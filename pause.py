import os
import sqlite3

from sqlite3 import Cursor

pause_connection = sqlite3.connect(os.getenv("QUEST_DB_PATH", "quest.db"))

with open('pause.sql') as pause_file:
    pause_connection.executescript(pause_file.read())
    cursor = pause_connection.cursor()
    existing_pause = cursor.execute("""
        SELECT pause
        FROM pause
    """).fetchone()
    if existing_pause is None:
        with pause_connection:
            cursor.execute("INSERT INTO pause VALUES (0)")

pause: bool = False

def read_pause() -> None:
    global pause
    cursor = pause_connection.cursor()
    pause = cursor.execute("""
        SELECT pause
        FROM pause
    """).fetchone()[0] == 1

def modify_pause(new_pause: bool) -> None:
    with pause_connection:
        cursor = pause_connection.cursor()
        cursor.execute(
            "UPDATE pause SET pause = ?",
            (1 if new_pause else 0,)
        )
    read_pause()

def pause_calls() -> None:
    modify_pause(True)

def resume_calls() -> None:
    modify_pause(False)

read_pause()
