CREATE TABLE IF NOT EXISTS call_log (
  user_id INTEGER NOT NULL,
  call_timestamp TEXT NOT NULL,
  phone TEXT NOT NULL,
  password TEXT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS call_log_user_lookup ON call_log (
  user_id,
  call_timestamp
);

CREATE INDEX IF NOT EXISTS call_log_timestamp_lookup ON call_log (
  call_timestamp
);
