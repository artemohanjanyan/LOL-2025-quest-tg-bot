CREATE TABLE IF NOT EXISTS phonebook (
  id INTEGER PRIMARY KEY,
  phone TEXT NOT NULL,
  password TEXT NULL,
  reply_n INTEGER,
  reply_type TEXT,
  reply_data TEXT
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS phone_lookup ON phonebook (
  phone,
  password,
  reply_n
);
