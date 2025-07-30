import sqlite3

from sqlite3 import Cursor
from dataclasses import dataclass
from typing import Dict
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

read_users()
