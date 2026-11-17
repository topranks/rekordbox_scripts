#!/usr/bin/env python3
"""
rb_memcues.py - add a memory cue at the position of every hot cue in a
rekordbox master.db, so older CDJs (where hot cues start playback rather than
setting the cue) get a memory cue at each of those points too.

Works on the djmdCue table, which is where rbxport reads cues from when it
exports to USB.

- Hot cues are Kind 1-3 and 5-17 (A-P); Kind 0 is a memory cue and Kind 4
  the active memory loop.
- Hot loops are skipped unless you pass --loops, in which case they are
  copied as memory loops.
- A memory cue is only added if the track has no memory cue/loop at that
  position already, so the script is safe to run again whenever you've set
  new hot cues.
- The new memory cue keeps the hot cue's comment but no colour.

Default is a dry run (the database is opened read-only). Add --apply to write;
a timestamped backup is made first. Close rbxport (and anything else using
the library) before applying.

The key is read from --key, the RB_DB_KEY environment variable, or prompted.

Requires: pip install sqlcipher3-wheels
written-by: claude
"""

import argparse
import getpass
import os
import random
import shutil
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:
    sys.exit("Missing sqlcipher3. Install with: pip install sqlcipher3-wheels")

HOT_KINDS = tuple(range(1, 4)) + tuple(range(5, 18))
MEMORY_KINDS = (0, 4)
MAX_CUE_ID = 1 << 32          # rekordbox cue IDs are decimals below 2^32
USN_TABLES = ("djmdContent", "djmdPlaylist", "djmdSongPlaylist",
              "djmdSongHotCueBanklist", "djmdCue")


def open_db(path, key, readonly):
    uri = f"file:{quote(str(path.resolve()))}" + ("?mode=ro" if readonly else "")
    con = sqlcipher.connect(uri, uri=True)
    con.execute("PRAGMA key = '{}'".format(key.replace("'", "''")))
    try:
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlcipher.DatabaseError:
        sys.exit("Could not read the database: wrong key, or not a SQLCipher file.")
    return con


def backup(db):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = db.with_name(f"{db.name}.bak-{stamp}")
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db) + suffix)
        if src.exists():
            shutil.copy2(src, str(dest) + suffix)
    print(f"Backup written to {dest} (+ -wal/-shm if present)")


def now_stamp():
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d} +00:00"


def is_loop(cue):
    out = cue["OutMsec"]
    return out is not None and out > (cue["InMsec"] or 0)


def plan(con, tolerance, loops):
    """Return (new_cues, stats); new_cues are dicts copied from hot cue rows."""
    con.row_factory = sqlcipher.Row
    rows = con.execute(
        "SELECT q.*, c.Title AS _title FROM djmdCue q "
        "JOIN djmdContent c ON c.ID = q.ContentID "
        "WHERE q.rb_local_deleted = 0 "
        "AND (c.rb_local_deleted IS NULL OR c.rb_local_deleted = 0) "
        "ORDER BY q.ContentID, q.InMsec").fetchall()

    by_track = defaultdict(list)
    for r in rows:
        by_track[r["ContentID"]].append(dict(r))

    stats = defaultdict(int)
    new = []
    for track, cues in by_track.items():
        hot = [c for c in cues if c["Kind"] in HOT_KINDS]
        if not hot:
            continue
        stats["tracks with hot cues"] += 1
        # positions already covered by a memory cue/loop (or added this run)
        taken = [(c["InMsec"], is_loop(c)) for c in cues if c["Kind"] in MEMORY_KINDS]
        added = 0
        for c in hot:
            if is_loop(c) and not loops:
                stats["hot loops skipped"] += 1
                continue
            if any(abs(c["InMsec"] - pos) <= tolerance and lp == is_loop(c)
                   for pos, lp in taken):
                stats["hot cues already covered"] += 1
                continue
            taken.append((c["InMsec"], is_loop(c)))
            new.append(c)
            added += 1
        if added:
            stats["tracks getting memory cues"] += 1
    stats["memory cues to add"] = len(new)
    return new, stats


def show(new, stats, limit=15):
    for k in ("tracks with hot cues", "tracks getting memory cues",
              "memory cues to add", "hot cues already covered", "hot loops skipped"):
        print(f"{k:<30} {stats.get(k, 0):>8}")
    if new:
        print("\nExamples:")
        for c in new[:limit]:
            letter = chr(ord("A") + (c["Kind"] - 1 if c["Kind"] <= 3 else c["Kind"] - 2))
            secs = c["InMsec"] / 1000
            what = "loop" if is_loop(c) else "cue "
            print(f"  {c['_title'] or c['ContentID']:<50.50}  hot {what} {letter} "
                  f"@ {int(secs // 60)}:{secs % 60:06.3f}")
        if len(new) > limit:
            print("  ...")


def next_usn(con):
    row = con.execute("SELECT int_1 FROM agentRegistry "
                      "WHERE registry_id = 'localUpdateCount'").fetchone()
    highest = (row[0] or 0) if row else 0
    for t in USN_TABLES:
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (t,)).fetchone():
            highest = max(highest, con.execute(
                f'SELECT COALESCE(MAX(rb_local_usn), 0) FROM "{t}"').fetchone()[0])
    return highest + 1, row is not None


def write(con, new):
    columns = [r[1] for r in con.execute('PRAGMA table_info("djmdCue")')]
    used_ids = {r[0] for r in con.execute("SELECT ID FROM djmdCue")}
    rng = random.SystemRandom()
    stamp = now_stamp()

    with con:   # single transaction
        usn, has_counter = next_usn(con)
        for c in new:
            while True:
                cid = str(rng.randrange(1, MAX_CUE_ID))
                if cid not in used_ids:
                    used_ids.add(cid)
                    break
            row = {k: c[k] for k in columns if k in c}
            row.update({
                "ID": cid,
                "Kind": 0,
                "Color": 255,             # memory cue with no colour
                "ColorTableIndex": 0,
                "ActiveLoop": 0,
                "UUID": str(uuid.uuid4()),
                "rb_data_status": 0,
                "rb_local_data_status": 0,
                "rb_local_deleted": 0,
                "rb_local_synced": 0,
                "usn": None,
                "rb_local_usn": usn,
                "created_at": stamp,
                "updated_at": stamp,
            })
            row = {k: v for k, v in row.items() if k in columns}
            cols = ", ".join(f'"{k}"' for k in row)
            marks = ", ".join("?" for _ in row)
            con.execute(f"INSERT INTO djmdCue ({cols}) VALUES ({marks})",
                        list(row.values()))
            usn += 1
        if has_counter:
            con.execute("UPDATE agentRegistry SET int_1 = ?, updated_at = ? "
                        "WHERE registry_id = 'localUpdateCount'", (usn - 1, stamp))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", type=Path, help="path to master.db")
    ap.add_argument("--key", help="SQLCipher key (or set RB_DB_KEY)")
    ap.add_argument("--loops", action="store_true",
                    help="also copy hot loops, as memory loops")
    ap.add_argument("--tolerance", type=int, default=1, metavar="MS",
                    help="treat an existing memory cue within this many ms as "
                         "the same point (default 1)")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if not args.db.is_file():
        sys.exit(f"{args.db} not found")
    key = args.key or os.environ.get("RB_DB_KEY") or getpass.getpass("master.db key: ")

    if args.apply and not args.no_backup:
        backup(args.db)

    con = open_db(args.db, key, readonly=not args.apply)
    new, stats = plan(con, args.tolerance, args.loops)
    show(new, stats)

    if not args.apply:
        print("\nDry run, nothing written. Re-run with --apply to add them.")
        return
    if not new:
        print("\nNothing to add.")
        return
    write(con, new)
    con.close()
    print(f"\nAdded {len(new)} memory cues.")


if __name__ == "__main__":
    main()
