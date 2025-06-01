#!/usr/bin/python3

import sys

from bs4 import BeautifulSoup
import argparse
import os
import copy
import urllib.parse
import re
import datetime

parser = argparse.ArgumentParser(description='Parse rekordbox XML and add new playlists with files converted to WAV')
parser.add_argument('--collection', '-c', help='Rekordbox exported XML file', type=str, default="/mnt/d/rekordbox_collection.xml")
parser.add_argument('--playlist_file', '-p', help='Text file with list of playlists to re-create with WAVs', required=True, type=str)
parser.add_argument('--outputdir', '-o', help='Directory to store converted files', type=str, default="/mnt/d/WAVIMPORT")
args = parser.parse_args()

def main():
    playlist_names = []
    with open(args.playlist_file, 'r') as playlist_file:
        for line in playlist_file.readlines():
            playlist_names.append(line.rstrip())

    print(f"Backing up {args.collection}... ", end='', flush=True)
    os.system(f'cp -b {args.collection} {args.collection}.bak')
    print("done.")

    print("Reading XML data... ", end='', flush=True)
    with open(f"{args.collection}", 'r', encoding="utf-8") as infile:
        soup = BeautifulSoup(infile.read(), "xml")
    print("done.")

    print("Getting existing playlists from XML...", end='')
    playlists = {}
    playlist_tracks = {}
    xml_playlists = soup.PLAYLISTS.find_all("NODE", Type="1")
    for xml_playlist in xml_playlists:
        playlists[xml_playlist['Name']] = []
        for track_id in xml_playlist.find_all("TRACK"):
            playlists[xml_playlist['Name']].append(track_id['Key'])
            playlist_tracks[track_id['Key']] = None
        # Delete old playlist
        xml_playlist.decompose()
    print("done.")

    sys.exit(0)

    # Get every track ID, so we can make sure to use unique one for our additions
    # Unsure if this is needed when removing existing items
    print("Reading track data...", end='')
    track_ids = []
    for track in soup.COLLECTION.find_all("TRACK"):
        # Record number so we know all existing IDs
        track_ids.append(int(track['TrackID']))
        # Save track data for later if it belongs to any playlist
        if track['TrackID'] in playlist_tracks:
            playlist_tracks[track['TrackID']] = copy.deepcopy(track)
        # Delete track from XML
        track.decompose()
    print("done.")

    # Max track ID so we use something higher
    last_trackid = sorted(track_ids)[-1]

    ## next we need to convert all tracks

    sys.exit(0)

    for track in playlist_tracks.values():
        newtrack = copy.deepcopy(track)
        xml_location = urllib.parse.unquote(newtrack['Location'])
        linuxpath = xml_location.lstrip('file://localhost/').replace('D:/', '/mnt/d/')
        if not os.path.isfile(linuxpath):
            # File in rekordbox playlist no longer exists, just skip
            continue
        filename = linuxpath.split('/')[-1]
        file_ext = filename.split(".")[-1]
        # Convert to WAV and add new track to XML collection
        wavfile = re.sub(f"{file_ext}$", "wav", filename, flags=re.IGNORECASE)
        wavpath = f"{args.outputdir}/{args.playlist}/{wavfile}"
        ffmpeg_cmd = f'ffmpeg -n -i "{linuxpath}" -sample_fmt s16 -ar 44100 "{wavpath}"'
        print(f"CMD: {ffmpeg_cmd}")
        os.system(ffmpeg_cmd)
        newtrack['Kind'] = "WAV File"
        newtrack['Size'] = os.path.getsize(wavpath)
        newtrack['BitRate'] = "1411"
        newtrack['SampleRate'] = "44100"
        newtrack['DateAdded'] = datetime.date.today().strftime('%Y-%m-%d')
        newtrack['Location'] = urllib.parse.quote(wavpath).replace('/mnt/d/', 'file://localhost/D:/')
        newtrack['TrackID'] = str(last_trackid + 1)
        # Copy existing hotcue's to new memory cue points for CDJ
        for hotcue in newtrack.find_all("POSITION_MARK", Type=0):
            if hotcue['Num'] != "-1":
                memory_cue = copy.deepcopy(hotcue)
                memory_cue['Num'] = "-1"
                del memory_cue['Red']
                del memory_cue['Green']
                del memory_cue['Blue']
                newtrack.append(memory_cue)

        soup.COLLECTION.append(newtrack)
        last_trackid += 1
        playlist_entry = soup.new_tag("TRACK", Key=newtrack['TrackID'])
        new_playlist.append(playlist_entry)

    # WAVIMPORT folder for new output playlist
    wav_imports = soup.PLAYLISTS.find("NODE", Name="WAVIMPORT", Type="0")
    wav_imports.append(new_playlist)
    
    print(f"Overwriting {args.collection}...")
    with open(f"{args.collection}", 'w', encoding="utf-8") as outfile:
        outfile.write(str(soup.prettify()))


if __name__ == "__main__":
    main()
