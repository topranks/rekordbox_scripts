1. [REKORDBOX] OUTPUT CURRENT COLLECTION AS XML:

- File... "EXPORT collection as XML"
** Overwrite D:\rekordbox_collection.xml
** When done back it up:  cp reckordbox_backup.xml rekordbox_backup.xml.bak


2. [BASH SHELL] MODIFY XML, MAKE A NEW WAV-BASED PLAYLIST FROM EXISTING ONE:

- sudo rekord_xml_play.py --playlist 2023-TARA-NICEROOTS --outputlist NEWROOTS_TARA
** Repeat as needed
** If something goes wrong you can overwrite rekordback_backup.xml with backup to reset.


3. [REKORDBOX] IMPORT WAVs AND EXPORT PLAYLISTS TO USB:

- Disable analysis of grid/bpm in settings in rekordbox (untick) & disable auto analysis
- Reload XML with little refresh icon (it will show loading)
- Find new playlists under IMPORT... WAVIMPORT
- Right click, EXPORT to E: (or USB)
- It will import, then export to USB
- When finished exporting to USB you can go to 'collection', sort by date added, remove all the WAVs
- Delete WAVs from disk
