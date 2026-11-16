#!/usr/bin/python3

import sqlite3
import os

def main():
    conn = sqlite3.connect('plaintext.db') 
    cursor = conn.cursor()
    #cursor.execute('''SELECT name FROM sqlite_master WHERE type="table";''')
    cursor.execute('''SELECT ID,FolderPath,FileNameL,Title FROM djmdContent''')
    #cursor.execute('''PRAGMA table_info(djmdContent);''')

    rows = cursor.fetchall()

    for row in rows:
        file_id = row[0]
        path = get_wsl_path(row[1])
        filename = row[2]
        title = row[3]

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
                            
                        update_statement = f'''UPDATE djmdContent \
                            SET FolderPath = "{win_dir}/{dirfile}", \
                                FileNameL = "{dirfile}" \
                            WHERE ID = {file_id};'''

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

