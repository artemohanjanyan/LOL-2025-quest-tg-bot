CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  role TEXT NOT NULL
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS users_usernames ON users (
  username
);
