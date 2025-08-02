import sqlite3

from sqlite3 import Cursor
from dataclasses import dataclass
from typing import Dict, List, Tuple
from enum import Enum

users_connection = sqlite3.connect('quest.db')

with open('users.sql') as users_file:
    users_connection.executescript(users_file.read())

class UserRole(Enum):
    ADMIN = "admin"
    CAPTAIN = "captain"

users: Dict[int, UserRole] = {}

def read_users() -> None:
    global users
    users = {}
    cursor = users_connection.cursor()
    cursor.execute("""
        SELECT user_id, role
        FROM users
    """)
    for user_id, role in cursor.fetchall():
        users[user_id] = UserRole(role)

def add_captain(user_id: str, username: str) -> None:
    cursor = users_connection.cursor()
    cursor.execute(
        "INSERT INTO users VALUES (?, ?, ?)",
        (user_id, username, UserRole.CAPTAIN.value)
    )
    users_connection.commit()
    read_users()

def list_users() -> List[Tuple[int, str, UserRole]]:
    cursor = users_connection.cursor()
    cursor.execute("""
        SELECT user_id, username, role
        FROM users
    """)
    return list(map(lambda x: (x[0], x[1], UserRole(x[2])), cursor.fetchall()))

read_users()
