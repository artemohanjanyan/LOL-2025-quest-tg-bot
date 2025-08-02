ALTER TABLE users
RENAME TO users_old;

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  role TEXT NOT NULL
) STRICT;

INSERT INTO users
SELECT user_id, username, role
FROM users_old;

DROP TABLE users_old;
