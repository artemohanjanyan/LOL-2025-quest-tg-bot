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

@dataclass
class User:
    user_id: int
    username: str
    role: UserRole

users: Dict[int, User] = {}
users_by_username: Dict[str, User] = {}

def read_users() -> None:
    global users
    global users_by_username
    users = {}
    cursor = users_connection.cursor()
    cursor.execute("""
        SELECT user_id, username, role
        FROM users
    """)
    for user_id, username, role in cursor.fetchall():
        users[user_id] = User(user_id, username, UserRole(role))
    users_by_username = { user.username: user for user in users.values() }

def add_captain(user_id: str, username: str) -> None:
    cursor = users_connection.cursor()
    cursor.execute(
        "INSERT INTO users VALUES (?, ?, ?)",
        (user_id, username, UserRole.CAPTAIN.value)
    )
    users_connection.commit()
    read_users()

def remove_captain(user_id: str) -> None:
    cursor = users_connection.cursor()
    cursor.execute(
        "DELETE FROM users WHERE user_id = ? and role = 'captain'",
        (user_id,)
    )
    users_connection.commit()
    read_users()

read_users()
