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
parser.add_argument('--playlist', '-p', help='Name of rekordbox playlist', required=True, type=str)
parser.add_argument('--outputlist', help='Name of generated playlist', type=str, default='')
parser.add_argument('--outputdir', '-o', help='Directory to store converted files', type=str, default="/mnt/d/WAVIMPORT")
args = parser.parse_args()

def main():
    print("Reading XML data...")
    with open(f"{args.collection}", 'r', encoding="utf-8") as infile:
        soup = BeautifulSoup(infile.read(), "xml")
      
    # Existing playlist element
    playlist = soup.PLAYLISTS.find("NODE", Name=args.playlist, Type="1")

    # New empty playlist element
    if args.outputlist:
        new_name = args.outputlist
    else:
        new_name = f"{args.playlist}_WAV"
    new_playlist = soup.new_tag("NODE", Name=new_name, Type="1", KeyType="0", Entries="0")

    try:
        os.makedirs(f"{args.outputdir}/{args.playlist}")
    except FileExistsError:
        pass

    # Get list of track_ids from playlist element
    playlist_tracks = {}
    for track_id in playlist.find_all("TRACK"):
        playlist_tracks[track_id['Key']] = {}

    # Get every track ID, so we can make sure to use unique one for our additions
    track_ids = []
    for track in soup.COLLECTION.find_all("TRACK"):
        track_ids.append(int(track['TrackID']))
        if track['TrackID'] in playlist_tracks.keys():
            playlist_tracks[track['TrackID']] = track

    # Max track ID so we use something higher
    last_trackid = sorted(track_ids)[-1]

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
        # Update the metadata we copied from the old file where we need to:
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
