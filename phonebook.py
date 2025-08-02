import sqlite3

from sqlite3 import Cursor
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from enum import Enum

phonebook_connection = sqlite3.connect('quest.db')

with open('phonebook.sql') as phonebook_file:
    phonebook_connection.executescript(phonebook_file.read())

class ReplyType(Enum):
    TEXT = "text"
    PHOTO = "photo"
    STICKER = "sticker"
    VOICE = "voice"
    DOCUMENT = "document"

@dataclass
class ReplyPart:
    reply_type: ReplyType
    reply_data: str

@dataclass
class Reply:
    parts: List[ReplyPart] = field(default_factory = list)

@dataclass
class Phonebook:
    replies: Dict[Tuple[str, str | None], Reply] = field(default_factory = dict)

phonebook = Phonebook()

def read_phonebook() -> None:
    global phonebook
    phonebook = Phonebook()
    cursor = phonebook_connection.cursor()
    cursor.execute("""
        SELECT phone, password, reply_type, reply_data
        FROM phonebook
        ORDER BY phone, password, reply_n ASC
    """)
    for phone, password, reply_type, reply_data in cursor.fetchall():
        if (phone, password) not in phonebook.replies:
            phonebook.replies[(phone, password)] = Reply()
        phonebook.replies[(phone, password)].parts.append(
                ReplyPart(ReplyType(reply_type), reply_data)
        )

read_phonebook()

def add_number(phone: str, password: str | None, reply: Reply) -> None:
    values = [(phone, password, reply_n,
               reply_part.reply_type.value, reply_part.reply_data)
              for reply_n, reply_part in enumerate(reply.parts)]
    cursor = phonebook_connection.cursor()
    execute_delete(cursor, phone, password)
    cursor.executemany("""
            INSERT INTO phonebook
            (phone, password, reply_n, reply_type, reply_data)
            VALUES (?, ?, ?, ?, ?)""",
            values
    )
    phonebook_connection.commit()
    read_phonebook()

def delete_number(phone: str, password: str | None) -> None:
    cursor = phonebook_connection.cursor()
    execute_delete(cursor, phone, password)
    phonebook_connection.commit()
    read_phonebook()

def execute_delete(cursor: Cursor, phone: str, password: str | None) -> None:
    if password is None:
        cursor.execute(
                "DELETE FROM phonebook WHERE phone = ? and password IS NULL",
                (phone,)
        )
    else:
        cursor.execute(
                "DELETE FROM phonebook WHERE phone = ? and password = ?",
                (phone, password)
        )
