import sqlite3

from sqlite3 import Cursor
from datetime import datetime

stats_connection = sqlite3.connect('quest.db')

with open('stats.sql') as stats_file:
    stats_connection.executescript(stats_file.read())

def log_call(user_id: int,
             call_timestamp: datetime,
             phone: str,
             password: str | None) -> None:
    cursor = stats_connection.cursor()
    cursor.execute("""
            INSERT INTO call_log
            (user_id, call_timestamp, phone, password)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, call_timestamp, phone, password)
    )
    stats_connection.commit()
