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
args = parser.parse_args()

def main():
    print("Reading XML data...")
    with open(f"{args.collection}", 'r', encoding="utf-8") as infile:
        soup = BeautifulSoup(infile.read(), "xml")
      
    # Find existing playlist element and delete
    playlist = soup.PLAYLISTS.find("NODE", Name=args.playlist, Type="1")
    playlist.decompose()
    
    print(f"Overwriting {args.collection}...")
    with open(f"{args.collection}", 'w', encoding="utf-8") as outfile:
        outfile.write(str(soup.prettify()))


if __name__ == "__main__":
    main()
