# Code review

Overall, the bot is small and understandable. SQLite remains a good fit by
scale, although MySQL or PostgreSQL can reasonably be chosen for better fault
isolation between unrelated writers. A large rewrite is not necessary first.
The new application-level E2E test confirms that the production path can be
tested effectively. The main remaining structural weakness is that Telegram
handling, business rules, process-wide state, and database access are tightly
coupled, which still makes resource lifecycle and test isolation awkward.

## Findings

The findings below are ordered by severity.

### 1. Expected malformed commands become unhandled exceptions

Checking `context.args is None` does not protect against an empty list. `/call`,
`/add_number`, `/progress`, `/add_captain`, `/remove_captain`, `/add_alias`, and
`/remove_alias` can raise `IndexError`; `/progress unknown-user` raises
`KeyError`. Examples are the [`/call` handler](bot.py#L209), [`/progress`
handler](bot.py#L363), and [captain administration](bot.py#L456). These should
return command-specific usage messages, not the generic "technical error."

### 2. Historical leaderboard data becomes incorrect after removing captains

[The leaderboard query](stats.py#L37) groups by columns from the left-joined
`users` table. Once [a captain is deleted](users.py#L49), all calls belonging to
missing users are grouped together as one anonymous user. Group by
`call_log.user_id` and fall back to that value, or soft-delete users or preserve
a username snapshot.

### 3. The progress display appears to use UTC as if it were local quest time

The incident report confirms that `Message.date` is UTC
([INCIDENT.md](INCIDENT.md#L13)), while [the progress handler](bot.py#L375)
calculates midnight and displayed clock time directly from it. If admins expect
Kyiv time, convert with `ZoneInfo("Europe/Kyiv")` before determining the day and
formatting it. This also matters for calls near midnight.

### 4. Some MarkdownV2 output is constructed unsafely

The number and password are [interpolated without escaping](bot.py#L269); `+`,
`-`, `.`, parentheses, underscores, backticks, and backslashes can produce
`BadRequest`. [The progress code block](bot.py#L405) also contains database
values without code-block escaping. Where `escape_markdown` is used, pass
`version=2` explicitly; its default is version 1. HTML parse mode is often
simpler for dynamically constructed output.

### 5. The long-action handler accepts unknown commands as message content

[The catch-all handler](bot.py#L584) uses `filters.TEXT`, which intentionally
includes commands. During a long action, an admin typo such as `/dnoe` becomes
part of the stored reply or broadcast. PTB recommends
`filters.TEXT & ~filters.COMMAND` when commands must be excluded: [PTB filters
documentation](https://docs.python-telegram-bot.org/en/stable/telegram.ext.filters.html#telegram.ext.filters.TEXT).
A `ConversationHandler` would also represent these states more explicitly.

### 6. Call deductions have no idempotency key

[The call log schema](stats.sql#L1) has neither a primary key nor `update_id`.
Telegram specifically exposes `update_id` to recognize repeated updates.
Because each call row costs a point, store it with a unique constraint so the
same update cannot deduct twice: [Telegram Update
documentation](https://core.telegram.org/bots/api#update). This does not change
the intentional delivery-before-recording policy.

That policy itself is reasonable, but its edge cases should be explicit:

- Delivery fails: no point deducted.
- A multipart reply fails halfway: partial reply, no point deducted.
- Delivery succeeds but recording fails: reply delivered, no point deducted,
  followed currently by "technical error."
- Telegram accepts delivery but its response is lost: likely delivered, no
  point deducted.

Exact atomicity across Telegram and SQLite is impossible; tests should preserve
the participant-favouring behavior already selected.

### 7. Imports perform database I/O and create global state

Importing [users.py](users.py#L9), [phonebook.py](phonebook.py#L9),
[stats.py](stats.py#L8), and [pause.py](pause.py#L6) opens four connections,
executes schema files, and loads caches. `QUEST_DB_PATH` now lets tests select a
temporary database, but it is read only during import, and the SQL file paths
remain relative to the current directory. The E2E test consequently has to set
the environment before dynamic imports and then remove those modules from
`sys.modules` ([test setup](tests/test_bot_e2e.py#L119)). Starting the bot from
another directory can still fail while opening the schema files.

Move connection creation, migrations, cache loading, and logging configuration
into explicit application startup. The four connections can initially remain;
injection and lifecycle control are the important improvements.

### 8. Schema evolution and invariants are weak

`CREATE TABLE IF NOT EXISTS` does not update existing tables, and
[migrate_users.sql](migrate_users.sql#L1) is a manual, non-idempotent migration.
Other examples include:

- `role` has no `CHECK` constraint.
- `reply_n`, `reply_type`, and `reply_data` are nullable in
  [phonebook.sql](phonebook.sql#L1).
- SQLite uniqueness does not treat two `NULL` passwords as equal.
- [pause.sql](pause.sql#L1) does not actually enforce a singleton row.

### 9. Project tooling is only partially reproducible

The project now has a pytest E2E test, separate
[development requirements](requirements-dev.txt), and documented uv setup and
test commands ([README.md](README.md#L3)). It still has no CI, `pyproject.toml`,
or lockfile. `python-telegram-bot` is pinned, while `python-dotenv`, pytest, and
pytest-asyncio are not. A `pyproject.toml` plus `uv.lock`, with pytest
dependencies in a development group, would make local and CI environments
fully reproducible.

The transaction scopes recently added are good, parameterized SQL is used
consistently, authorization is based on stable Telegram IDs, and the
participant-favouring reply-before-record rule is documented. The application
factory, explicit datetime serialization, and first E2E scenario are also solid
incremental improvements.

## Recommended structure

Use a small three-layer design rather than a framework-heavy rewrite:

- **Telegram adapter:** parses `Update`, validates syntax, renders replies, and
  contains PTB handler registration.
- **Quest service:** owns authorization, pause policy, phone lookup,
  delivery-before-recording policy, and broadcast workflow. It should not import
  Telegram or SQLite types.
- **Quest store:** an injected interface with a SQLite implementation. At this
  project's size, one `QuestStore` protocol is enough; interfaces for every
  table would add unnecessary ceremony.

The new [`create_application(token, request=None)` factory](bot.py#L546)
already separates handler registration from `run_polling()` and provides the
Telegram transport seam needed by tests. Retain it, and extend application
startup with explicit settings and storage ownership. `main()` should only load
configuration, construct resources, run migrations, create the application,
and close resources on shutdown. Handler objects or closures can receive the
service directly; `application.bot_data` is another PTB-native injection point.

Because the datasets are tiny, consider removing the global
users/phonebook/pause caches and querying SQLite directly. That eliminates
stale-data behavior and the `/read_*` maintenance commands. If retained, hide
caching inside the store and invalidate it automatically.

## Testing approach

**The preferred strategy for this project is black-box, in-process Application
E2E testing through user-facing Telegram operations.** This suite should be the
initial priority; separate service unit tests, repository tests, lock/restart
tests, and live-Telegram smoke tests are not currently required.

A working proof of this approach now exists in
[`tests/test_bot_e2e.py`](tests/test_bot_e2e.py#L119). It configures a captain
and phonebook entry, sends `/call` and `/status` through real PTB update
processing, exercises the real file-backed SQLite modules, and asserts only the
messages visible to that captain.

The important property is that these tests run as much production code as
possible: the real `Application`, handler registration and selection, command
parsing, authorization, long-action state, business rules, database modules,
schema, SQL, and transaction handling. **Do not replace the service, repository,
or SQLite database with mocks merely to make the tests easier.** Use a separate
temporary file-backed SQLite database for each test so that all four production
connections share the same database. Direct database setup should be limited to
unavoidable bootstrap data, such as the first administrator and quest fixtures.

**The only intended fake is the external Telegram Bot API boundary.** A fake PTB
`BaseRequest` should accept the requests produced by the real PTB `Bot`, record
outgoing messages and media, and return valid Bot API JSON. This is necessarily
a test double: completely mock-free automation would require a live Telegram
bot plus an automated ordinary Telegram user, which would be slow, brittle, and
dependent on an external service.

PTB exposes the necessary seams:

- Build real `Update` objects from representative Telegram JSON.
- Inject a fake implementation of
  [`BaseRequest`](https://docs.python-telegram-bot.org/en/v22.3/telegram.request.baserequest.html)
  through
  [`ApplicationBuilder.request()`](https://docs.python-telegram-bot.org/en/v22.3/telegram.ext.applicationbuilder.html#telegram.ext.ApplicationBuilder.request).
- Have it record `sendMessage`, `sendPhoto`, and other calls and return valid Bot
  API JSON.
- Initialize the real application and pass the update through
  [`Application.process_update()`](https://docs.python-telegram-bot.org/en/v22.3/telegram.ext.application.html#telegram.ext.Application.process_update).

Conceptually:

```python
application = create_application("test-token", request=fake_api)
async with application:
    captain = TelegramUser(application, captain_id, "test_captain")
    await captain.send("/call 12345 answer")
    await captain.send("/status")

assert fake_api.messages_to(captain_id) == expected_messages
```

Assertions should preferably stay at that user-facing boundary: inspect what
the fake Telegram API would have delivered, and use commands such as `/status`,
`/progress`, and `/leaderboard` to observe persisted effects. Direct SQL
assertions may still be useful for diagnosing a failed test, but should not be
the main expression of expected behavior.

This exercises the production path from a Telegram-shaped `Update` through PTB
routing and the real database to the outgoing Bot API call. It intentionally
does not test polling, HTTP/TLS, Telegram's servers, or client rendering.
Mocking `getUpdates` and running the polling loop would mostly test PTB itself
rather than this application.

For SQLite, remember that each plain `sqlite3.connect(":memory:")` creates a
separate database. Therefore these application tests should use something like
`tmp_path / "quest.db"`, not `:memory:`, while retaining the production
connection arrangement. [SQLite documents this distinction
explicitly](https://www.sqlite.org/inmemorydb.html).

PTB supplies the public injection points above, but no supported, ready-made
in-memory Telegram test server. The current project-specific
`FakeTelegramRequest` and `TelegramUser` implement the minimal `getMe`,
`sendMessage`, incoming-command, and message-timeline behavior needed by the
first scenario; extend them only as new scenarios require more Bot API methods.

The dynamic imports and `sys.modules` cleanup in the current test are a
temporary consequence of finding 7, not part of the preferred testing API.
Once database initialization and shutdown are explicit, tests should import the
application normally and let fixtures own the storage lifecycle.

The successful known-number call and visible `/status` deduction are covered.
The next highest-value test cases are:

- Unknown numbers and incorrect passwords.
- Paused and unauthorized calls.
- Missing or malformed arguments.
- Telegram delivery failure leaves call count unchanged.
- Database failure after successful delivery leaves call count unchanged and
  the connection reusable.
- Duplicate `update_id` does not deduct twice.
- Multipart failure after one successful part.
- Broadcast completion clears state.
- Partial broadcast failure and retry do not duplicate deliveries.
- Markdown-special values.
- Removed users remain distinct in history.
- Kyiv date boundaries and daylight-saving changes.

## SQLite versus MySQL or PostgreSQL

SQLite is adequate for the current volume: there is one bot process, updates
are effectively processed one at a time, and `/call` performs one short insert.
This is within SQLite's intended use. SQLite itself recommends a client/server
database primarily for many simultaneous writers, multiple machines directly
sharing data, or write-intensive multi-server systems: [SQLite appropriate-use
guidance](https://www.sqlite.org/whentouse.html).

There is nevertheless a valid availability argument for MySQL or PostgreSQL.
SQLite permits only one writer for the entire database. An unfinished write
transaction in `phonebook`, `users`, or `pause` can therefore prevent an
unrelated insert into `call_log`. MySQL's default InnoDB engine instead uses
row-level locking and MVCC. A transaction affecting one table or set of rows
normally does not prevent unrelated writes elsewhere: [MySQL InnoDB
overview](https://dev.mysql.com/doc/refman/8.4/en/innodb-introduction.html).
If the previous incident was caused by an unfinished write on one of the other
SQLite connections, InnoDB would probably have contained its impact and allowed
call recording to continue.

This improves fault isolation rather than guaranteeing availability:

- A leaked connection with no active transaction generally holds no data
  locks; it consumes a connection. A leaked connection with an unfinished
  transaction is the dangerous case.
- An InnoDB transaction can still block operations touching the same rows,
  index ranges, or table metadata.
- InnoDB can deadlock, including during apparently simple inserts or deletes.
  The application must be prepared to roll back and retry the whole
  transaction: [MySQL deadlock
  guidance](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks-handling.html).
- Leaked connections can exhaust the client pool or the server's
  `max_connections`, preventing new work: [MySQL connection-limit
  documentation](https://dev.mysql.com/doc/refman/8.4/en/too-many-connections.html).
- A database server adds network, service-startup, credential, backup, and
  operational failure modes that an embedded SQLite database does not have.

A server database also makes lock diagnosis easier. For example, MySQL exposes
the waiting and blocking transaction, statement, table, and lock age through
its [`innodb_lock_waits`
views](https://dev.mysql.com/doc/refman/8.4/en/sys-innodb-lock-waits.html), and an
operator can terminate a blocking session.

An accidental second bot process is not made safe merely by switching
databases. Two long-polling instances using the same token conflict, and the
current users, phonebook, pause, and long-action state are held independently
in each process. An intentional multi-instance design would additionally need:

- webhook-based routing rather than competing pollers;
- shared or uncached application state;
- a unique `update_id` constraint to prevent double deductions; and
- a deliberate concurrency model for per-user long actions.

MySQL is therefore a reasonable choice if a dependable server is already
operated, a managed instance is available, or fault containment during a
time-critical quest is worth the extra infrastructure. PostgreSQL provides the
same relevant class of benefit; existing expertise and infrastructure matter
more here than choosing between the two. If the database would be another
lightly managed service on the same machine, SQLite may remain the more reliable
overall system despite its coarse write lock.

Before either retaining SQLite or migrating:

- Introduce the `QuestStore` boundary so database-specific code is isolated.
- Make connection creation and shutdown explicit and keep transactions short.
- Add versioned migrations and automated backups.
- Store `update_id` and a separate database insertion timestamp.
- Add bounded retries for transient lock or deadlock failures.
- Enforce one bot instance unless multi-instance behavior is intentionally
  designed.

If SQLite is retained, explicitly configure and report the busy timeout and
consider WAL mode. WAL lets readers and a writer overlap, but still permits only
one writer, so it is useful resilience rather than a cure for the old incident:
[SQLite WAL documentation](https://www.sqlite.org/wal.html).

If MySQL is selected, use a small bounded connection pool with acquisition and
lock timeouts, rollback connections before returning them to the pool, and
retry complete transactions after deadlocks. The preferred Application E2E
tests should use a disposable real MySQL instance for database-specific
concurrency and locking scenarios; an in-memory fake or SQLite test database
cannot validate the behavior motivating the migration.

The application factory and first E2E scenario are now in place. The suggested
next order is: expand the user-facing E2E suite around the concrete findings,
make storage initialization and shutdown explicit, fix the confirmed behavior,
and then choose the production database. SQLite is sufficient by scale, while
MySQL or PostgreSQL is defensible as an availability and fault-isolation choice.
