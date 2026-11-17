#!/usr/bin/env python3
r"""
rb_repath.py - rewrite path prefixes in a rekordbox master.db, e.g. so a
Windows library can be used on Linux (with rbxport).

Default is a dry run: it scans every text column of every table for values
starting with an --old prefix and shows what they would become. Add --apply
to write.

--old/--new can be repeated; they are paired in the order given. Matching of
--old ignores letter case and treats / and \ as the same.

Slashes in the rest of the path are left alone unless you ask:
    --tounix   backslashes -> forward slashes
    --todos    forward slashes -> backslashes

Example:
    ./rb_repath.py /media/sabtemp/rbxport_library/master.db \
        --old 'E:\Music' --new /media/stuff/Music --tounix

    ./rb_repath.py ... --old 'E:\Music' --new /media/stuff/Music --tounix --apply

The key is read from --key, the RB_DB_KEY environment variable, or prompted.

Requires: pip install sqlcipher3-wheels

Written by: claude
"""

import argparse
import getpass
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:
    sys.exit("Missing sqlcipher3. Install with: pip install sqlcipher3-wheels")

WIN_PATH_GLOB = "[A-Za-z]:[/\\]*"   # GLOB: backslash is literal inside []
SAMPLES = 3


# ---------------------------------------------------------------- path rules

def strip_sep(p):
    return p.rstrip("/\\")


def build_rules(olds, news):
    if len(olds) != len(news):
        sys.exit(f"Got {len(olds)} --old but {len(news)} --new; they must come in pairs.")
    if not olds:
        sys.exit("Give at least one --old/--new pair.")
    # (old prefix normalised to '/', new prefix); longest old first so more
    # specific rules win
    rules = [(strip_sep(o).replace("\\", "/"), strip_sep(n)) for o, n in zip(olds, news)]
    rules.sort(key=lambda r: len(r[0]), reverse=True)
    return rules


def convert_slashes(s, mode):
    if mode == "tounix":
        return s.replace("\\", "/")
    if mode == "todos":
        return s.replace("/", "\\")
    return s


def rewrite(value, rules, mode):
    """Return the rewritten value, or None if no rule matches."""
    low = value.replace("\\", "/").lower()
    for old, new in rules:
        o = old.lower()
        if low == o or low.startswith(o + "/"):
            rest = value[len(old):]          # same length: only slashes differ
            return convert_slashes(new + rest, mode)
    return None


# ---------------------------------------------------------------- database

def open_db(path, key):
    con = sqlcipher.connect(str(path))
    con.execute("PRAGMA key = '{}'".format(key.replace("'", "''")))
    try:
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlcipher.DatabaseError:
        sys.exit("Could not read the database: wrong key, or not a SQLCipher file.")
    return con


def columns(con):
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        for row in con.execute(f'PRAGMA table_info("{t}")'):
            yield t, row[1]


def like_escape(s):
    return s.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def scan(con, rules):
    """Return (matches, other_win_paths).

    matches:  {(table, col): [(rowid, value), ...]} values starting with an --old
    others:   Counter of (table.col, prefix) for Windows-style paths not matched
    """
    matches, others = {}, Counter()
    patterns = [like_escape(old) + "%" for old, _ in rules]
    where = " OR ".join(
        ["replace(\"{c}\", '\\', '/') LIKE ? ESCAPE '!'"] * len(patterns))
    for table, col in columns(con):
        try:
            rows = con.execute(
                f'SELECT rowid, "{col}" FROM "{table}" '
                f'WHERE typeof("{col}")=\'text\' AND ({where.format(c=col)})',
                patterns).fetchall()
            win = con.execute(
                f'SELECT "{col}" FROM "{table}" '
                f'WHERE typeof("{col}")=\'text\' AND "{col}" GLOB ?',
                (WIN_PATH_GLOB,)).fetchall()
        except sqlcipher.OperationalError:
            continue   # e.g. a WITHOUT ROWID table
        rows = [(rid, v) for rid, v in rows if rewrite(v, rules, None) is not None]
        if rows:
            matches[(table, col)] = rows
        for (v,) in win:
            if rewrite(v, rules, None) is None:
                parts = v.replace("\\", "/").split("/")
                others[(f"{table}.{col}", "/".join(parts[:2]))] += 1
    return matches, others


# ---------------------------------------------------------------- reporting

def report(matches, others, rules, mode):
    total = 0
    print(f"{'table.column':<45} {'matches':>8}")
    print("-" * 55)
    for (table, col), rows in matches.items():
        total += len(rows)
        print(f"{table + '.' + col:<45} {len(rows):>8}")
        for _, old in rows[:SAMPLES]:
            print(f"    {old}\n -> {rewrite(old, rules, mode)}")
    print("-" * 55)
    print(f"{'TOTAL':<45} {total:>8}")

    if others:
        print("\nOther Windows-style paths that will be left unchanged "
              "(column, prefix, count):")
        for (col, pfx), n in others.most_common(30):
            print(f"    {col:<40} {pfx:<35} {n}")
    return total


# ---------------------------------------------------------------- verification

def find_case_insensitive(path):
    """Return the real path if it exists with different letter case, else None."""
    p = Path(path)
    cur = Path(p.anchor)
    for part in p.parts[1:]:
        cand = cur / part
        if cand.exists():
            cur = cand
            continue
        try:
            hits = [c for c in os.listdir(cur) if c.lower() == part.lower()]
        except OSError:
            return None
        if not hits:
            return None
        cur = cur / hits[0]
    return str(cur)


def verify_tracks(con, limit=25):
    try:
        rows = con.execute(
            "SELECT ID, FolderPath FROM djmdContent "
            "WHERE FolderPath LIKE '/%' "
            "AND (rb_local_deleted IS NULL OR rb_local_deleted = 0)").fetchall()
    except sqlcipher.OperationalError:
        rows = con.execute(
            "SELECT ID, FolderPath FROM djmdContent "
            "WHERE FolderPath LIKE '/%'").fetchall()
    if not rows:
        return

    missing, case_only = [], []
    for track_id, path in rows:
        if os.path.exists(path):
            continue
        real = find_case_insensitive(path)
        (case_only if real else missing).append((track_id, path, real))

    print(f"\nChecked {len(rows)} track paths: "
          f"{len(rows) - len(missing) - len(case_only)} found, "
          f"{len(case_only)} differ only in letter case, {len(missing)} missing.")
    for track_id, path, real in case_only[:limit]:
        print(f"  CASE  {track_id}: {path}\n          on disk: {real}")
    for track_id, path, _ in missing[:limit]:
        print(f"  MISS  {track_id}: {path}")
    if len(case_only) + len(missing) > 2 * limit:
        print("  ...")


# ---------------------------------------------------------------- main

def backup(db):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = db.with_name(f"{db.name}.bak-{stamp}")
    # Keep SQLite's naming so the backup opens together with its WAL
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db) + suffix)
        if src.exists():
            shutil.copy2(src, str(dest) + suffix)
    print(f"Backup written to {dest} (+ -wal/-shm if present)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", type=Path, help="path to master.db")
    ap.add_argument("--old", action="append", default=[], metavar="PREFIX",
                    help=r"path prefix to replace, e.g. 'E:\Music' (repeatable)")
    ap.add_argument("--new", action="append", default=[], metavar="PREFIX",
                    help="replacement prefix, e.g. /media/stuff/Music (repeatable)")
    slashes = ap.add_mutually_exclusive_group()
    slashes.add_argument("--tounix", dest="mode", action="store_const", const="tounix",
                         help=r"convert \ to / in rewritten paths")
    slashes.add_argument("--todos", dest="mode", action="store_const", const="todos",
                         help=r"convert / to \ in rewritten paths")
    ap.add_argument("--key", help="SQLCipher key (or set RB_DB_KEY)")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--verify-only", action="store_true",
                    help="only check that track paths exist on disk")
    args = ap.parse_args()

    if not args.db.is_file():
        sys.exit(f"{args.db} not found")
    rules = None if args.verify_only else build_rules(args.old, args.new)
    key = args.key or os.environ.get("RB_DB_KEY") or getpass.getpass("master.db key: ")

    if args.apply and not args.no_backup:
        backup(args.db)

    con = open_db(args.db, key)

    if args.verify_only:
        verify_tracks(con)
        return

    matches, others = scan(con, rules)
    total = report(matches, others, rules, args.mode)

    if not args.apply:
        print("\nDry run, nothing written. Re-run with --apply to update.")
        return
    if not total:
        sys.exit("\nNothing matched; nothing written.")

    with con:   # single transaction, rolled back on error
        for (table, col), rows in matches.items():
            for rowid, val in rows:
                con.execute(f'UPDATE "{table}" SET "{col}" = ? WHERE rowid = ?',
                            (rewrite(val, rules, args.mode), rowid))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(f"\nUpdated {total} values and checkpointed the WAL into master.db.")

    verify_tracks(con)
    con.close()


if __name__ == "__main__":
    main()
