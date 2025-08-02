import sqlite3

from sqlite3 import Cursor
from datetime import datetime
from typing import List, Tuple

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

def status(user_id: int) -> int:
    cursor = stats_connection.cursor()
    cursor.execute("""
        SELECT COUNT(*)
        FROM call_log
        WHERE user_id = ?
    """, (user_id,))
    call_n, = cursor.fetchone()
    return call_n

def stats() -> List[Tuple[int, str | int, str]]:
    cursor = stats_connection.cursor()
    cursor.execute("""
        SELECT COUNT(*) as call_n, IFNULL(users.username, users.user_id), role
        FROM call_log LEFT JOIN users ON call_log.user_id = users.user_id
        GROUP BY users.user_id, username, role
        ORDER BY role DESC, call_n ASC
    """)
    return cursor.fetchall()

def progress(user_id: int) -> List[Tuple[str, str | None, datetime]]:
    cursor = stats_connection.cursor()
    cursor.execute("""
        SELECT phone, password, MIN(call_timestamp) AS first_call
        FROM call_log
        WHERE user_id = ?
        GROUP BY phone, password
        ORDER BY first_call ASC
    """, (user_id,))
    return list(map(
        lambda row: (row[0], row[1], datetime.fromisoformat(row[2])),
        cursor.fetchall()
    ))
