# SQLite locking incident — 2025-08-17

## Summary

During the quest, call recording stopped for about 16 minutes. The recovered log
contains 27 instances of `sqlite3.OperationalError: database is locked`, all raised
by the `INSERT` in `stats.log_call()`. Restarting the bot cleared the condition.

The exact connection or process that initially acquired the write lock is unknown.

## Timeline

`call_log.call_timestamp` comes from Telegram's UTC `message.date`; it is not the
database insertion time. Converted to Kyiv time, the database contains three calls
confirmed to have been recorded before or at the start of the incident:

- 10:41:28
- 10:42:28
- 10:42:37

The next recorded call is at 10:59:11, leaving a 16 minute 33 second gap.

The captured application errors run from approximately 10:40:52 through 10:54:10
Kyiv time. Shell history shows `python bot.py` being started again at 10:54:12.
The small mismatch between application and Telegram timestamps is consistent with
clock drift: shell history shows `systemd-timesyncd` being enabled on 2025-10-20.

## What is known

- SQLite was using `delete` journal mode, and the recovered database passes
  `PRAGMA integrity_check`.
- The bot keeps four process-wide SQLite connections: users, phonebook, stats, and
  pause.
- Telegram updates are processed sequentially by default. The participant paths
  `/call` and `/status` do not perform concurrent database work; only `/call` writes.
- Every recovered traceback fails at `stats_connection.execute()`, not at
  `commit()`. This strongly indicates that a different connection already held a
  write transaction.
- The pause initialization cursor was tested and ruled out as a retained lock.
  A serial stress test of 10,000 calls using the same four-connection structure also
  completed without contention.
- No admin content changes or additional bot instance are known to have been active
  during the incident. SQLite CLI sessions recorded afterward contained diagnostic
  reads and no explicit transaction commands.
- The reply is intentionally sent before the call is inserted into the database.
  Therefore, these failed inserts did not deduct points from participants, although
  some replies may already have been delivered.

## Assessment

A previously stuck transaction from before the quest does not fit the three confirmed
successful writes immediately before the outage. Participant traffic in a single bot
process also cannot, by itself, create a competing writer with the current sequential
code. Possible explanations include an unexpected write on another global connection,
an external SQLite client or process, or runtime state not preserved in the available
logs. There is not enough evidence to select one conclusively.

The code did contain a real transaction-safety issue: writes called `commit()` only on
success and never rolled back exceptions. That could prolong or amplify contention,
but it is not proven to have initiated this incident.

## Remediation

- All writes now use `with connection:` transaction scopes, which commit on success
  and roll back on exceptions (`5a830d2`).
- The four global connections were intentionally retained.
- The reply-before-recording order is documented because it deliberately favors the
  participant when Telegram delivery fails.

If the bot is used for another quest, useful additional diagnostics would be an actual
database insertion timestamp, process ID, and each connection's `in_transaction` state
whenever an SQLite error occurs. Single-instance enforcement would also remove another
possible source of competing writers. WAL mode or a longer busy timeout may improve
resilience but would not replace transaction cleanup or identify the original cause.
