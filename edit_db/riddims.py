#!/usr/bin/python3

import sqlite3
import os
import sys

def main():
    conn = sqlite3.connect('plaintext.db') 
    cursor = conn.cursor()
    #cursor.execute('''SELECT name FROM sqlite_master WHERE type="table";''')
    cursor.execute('''SELECT ID,FolderPath,Title,Commnt,ReleaseYear,LabelID FROM djmdContent''')
    #cursor.execute('''PRAGMA table_info(djmdLabel);''')

    rows = cursor.fetchall()


    for row in rows:
        file_id = row[0]
        path = get_wsl_path(row[1])
        title = row[2]
        comment = row[3]
        db_year = int(row[4])
        label_id = row[5]

        if "REGGAE RIDDIMS" in path:
            try:
                directory = path.split("/")[-2]
                year = directory.split()[0]
                riddim = directory.split("-")[1]
                if "(" in riddim:
                    riddim_name = riddim.split("(")[0].upper().replace("RIDDIM", "").strip()
                    # label_name = riddim.split("(")[1].replace(")", "").upper()
                else:
                    riddim_name = riddim.upper().replace("RIDDIM", "").strip()
                    # label_name = ""
            except:
                print(f"Problem with {path}") 

            try:
                changed = False
                if "www" in comment.lower() or "http" in comment.lower() or "mp3" in comment.lower() or len(comment) <= 1 or \
                        "mediaz" in comment.lower() or "blogspot" in comment.lower():
                    update_statement = f'''UPDATE djmdContent \
                        SET Commnt="{riddim_name}" \
                        WHERE ID = {file_id};'''
                    print(" ".join(update_statement.split()))
                    cursor.execute(update_statement)
                    changed = True
            except Exception as e:
                print(f"Problem setting comment {riddim_name} on {path} {e}")

            try:
                if len(str(db_year)) < 4 or db_year < 1950 or db_year > 2021:
                    year = int(year)
                    update_statement = f'''UPDATE djmdContent \
                        SET ReleaseYear="{int(year)}" \
                        WHERE ID = {file_id};'''
                    
                    print(" ".join(update_statement.split()))
                    cursor.execute(update_statement)
                    changed = True
            except:
                print(f"Problem setting year to {year} for {path}")

                # NOT DOING LABELS AS IT'S A SEPARATE TABLE AND WOULD NEED TO GENERATE NEW IDs ETC
#                if label_name != "":
#                    cursor.execute(f'''SELECT ID,Name FROM djmdLabel WHERE ID = {label_id} LIMIT 10;''')
#                    label_rows = cursor.fetchall()
#                    for label_row in label_rows:
#                        db_label = label_row[1]
##                        print(f"db_label {db_label}")
#                        if len(db_label) < 2:
#                            print(f"Updating Label from {db_label} to {label_name} for {riddim_name}")



            if changed:
                conn.commit()

    cursor.close()

    '''
        try:
            os.stat(path)
        except FileNotFoundError:
            directory = "/" + "/".join(path.split("/")[1:-1])
            try:
                dirfiles = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
                gotit = False
                for dirfile in dirfiles:
                    if title.lower() in dirfile.lower():
                        win_dir = get_win_path(directory)
        '''                     
#                        update_statement = f'''UPDATE djmdContent \
#                            SET FolderPath = "{win_dir}/{dirfile}", \
#                                FileNameL = "{dirfile}" \
#                            WHERE ID = {file_id};'''
    '''
                        print(" ".join(update_statement.split()))
                        cursor.execute(update_statement)
                        gotit = True
                        break

                        # TODO - ID3 Check if filename doesn't help

                if gotit:
                    conn.commit()
                    pass
                else:
                    print(f"{path} didn't have obvious candidate")

            except FileNotFoundError:
                print(f"Directory {directory} doesn't seem to exist.")

    

    cursor.close()

    '''

def get_win_path(wsl_path):
    split_path = wsl_path.split("/")
    directory = split_path[2].upper()
    
    return f'{directory}:/{"/".join(split_path[3:])}'
    

def get_wsl_path(win_path):
    ''' Retruns relative WSL path of a file from a Windows one '''

    path_split = win_path.split(":")
    drive = path_split[0].lower()
    linux_path = f"/mnt/{drive}"
    return (linux_path + path_split[1])


if __name__ == "__main__":
    main()

