# Design plan for the next quest bot

## Recommendation

Keep the next bot small, but give it explicit boundaries from the beginning:

```text
Telegram update -> feature handler -> QuestService -> QuestStore -> SQLite
                                      -> delivery port -> Telegram Bot API
```

The handlers should contain Telegram-specific validation and presentation, the
service should contain quest rules, and one explicitly owned store should
contain all database access. This is enough structure for a bot of this size;
separate interfaces for every table or a large dependency-injection framework
would add ceremony without much benefit.

The most important improvements over the current bot are:

- no database work, logging setup, or cache loading during imports;
- one composition root that creates and closes every resource;
- command handlers split by feature while their registration order remains
  visible in one place;
- schema migrations and constraints designed before the quest data is loaded;
- application E2E tests present before most admin functionality is added;
- a packaged uv project with `pyproject.toml` and a committed `uv.lock`;
- mypy annotations and reasonably strict checking from the first module;
- one committed pre-commit suite for the lockfile, formatting, linting, types,
  and tests;
- GitHub Actions running that same suite for the current `main` head and every
  pull request; and
- a linked CI status badge near the top of `README.md`.

### Scope constraints

Design for one bot deployment, one quest, and one run of that quest. Use a
separate database and deployment for another quest; do not add tenant IDs,
quest IDs, run IDs, tenant routing, or reusable historical reporting machinery.

Use UTC everywhere: Telegram timestamps, database values, calculations,
reports, logs, and displayed times. There is no configurable quest timezone.

Do not restrict the bot to private chats in application code. Whether users may
add it to groups is an operational or product choice controlled through
BotFather and may intentionally be enabled. Likewise, preserving leaderboard
identity after a captain is removed is not a requirement for this single-run
bot; hard deletion and limited historical reporting are acceptable.

## Suggested project layout

```text
next-quest-bot/
├── .github/
│   └── workflows/
│       └── checks.yml
├── .pre-commit-config.yaml
├── pyproject.toml
├── uv.lock
├── .python-version
├── README.md
├── src/
│   └── quest_bot/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       ├── config.py
│       ├── models.py
│       ├── service.py
│       ├── delivery.py
│       ├── handlers/
│       │   ├── registry.py
│       │   ├── common.py
│       │   ├── captain.py
│       │   └── admin/
│       │       ├── users.py
│       │       ├── content.py
│       │       ├── operations.py
│       │       └── reports.py
│       └── storage/
│           ├── base.py
│           ├── sqlite.py
│           └── migrations/
│               ├── 001_initial.sql
│               └── 002_add_*.sql
└── tests/
    ├── support/
    │   └── telegram.py
    └── e2e/
        ├── test_calls.py
        ├── test_admin_content.py
        └── test_broadcasts.py
```

Place migrations inside the package and read them with `importlib.resources`.
They will then work regardless of the process's current directory and will be
included in the installed application. uv's build backend always includes the
module directory and its small data files by default:
[uv build-backend documentation](https://docs.astral.sh/uv/concepts/build-backend/).

### Responsibilities

- `__main__.py` loads settings, opens the store, builds the service and PTB
  application, runs polling, and closes the store in `finally` or a context
  manager. It should contain almost no quest behavior.
- `app.py` contains `create_application(...)` and explicit handler
  registration. It accepts production dependencies and an optional PTB request
  implementation for tests.
- `config.py` contains a validated `Settings` dataclass. Read environment
  variables once at startup; do not read them throughout the codebase.
- `service.py` owns authorization-independent quest rules such as phone lookup,
  pause behavior, delivery-before-recording, idempotency, and broadcast
  progress. Authorization policy may also live here if it is more than a
  simple role check.
- `delivery.py` adapts domain reply parts to Telegram operations. It is where
  text parse modes, escaping, and media delivery are centralized.
- `storage/base.py` defines one small `QuestStore` protocol. `storage/sqlite.py`
  implements it and owns the connection, migrations, transactions, and row
  mapping.
- `handlers/` translates PTB updates into service calls and service results
  into user-visible responses. Handlers should not issue SQL.

## Splitting command definitions

Split the admin surface by workflow, not into one enormous `admin.py`:

- `captain.py`: `/call`, `/status`, and captain help;
- `admin/users.py`: adding, removing, and listing captains;
- `admin/content.py`: phonebook entries, aliases, and reply construction;
- `admin/operations.py`: pause/resume and broadcasts;
- `admin/reports.py`: leaderboard and progress views.

Each module should expose a small, side-effect-free function such as
`build_handlers(dependencies)`. `registry.py` calls those functions in an
intentional order and adds the returned handlers to the application:

```python
# handlers/captain.py
def build_handlers(deps: Dependencies) -> list[BaseHandler]:
    return [
        CommandHandler("call", partial(call, service=deps.service)),
        CommandHandler("status", partial(status, service=deps.service)),
    ]


# handlers/registry.py
HANDLER_MODULES = (
    captain,
    admin_users,
    admin_content,
    admin_operations,
    admin_reports,
)


def register_handlers(application: Application, deps: Dependencies) -> None:
    for module in HANDLER_MODULES:
        for handler in module.build_handlers(deps):
            application.add_handler(handler)
```

The exact implementation may use small handler classes instead of `partial`;
the important properties are explicit dependencies, no registration during
import, and one visible place controlling handler order. Do not introduce a
dynamic plugin system for a fixed set of commands.

Keep each command's name, Telegram menu description, required role, and usage
text close together. The registry can aggregate this metadata to build `/help`
and call `set_my_commands()`, avoiding three independent command lists.

Put role checks in one wrapper or helper in `common.py` instead of repeating
subtly different permission code in every callback. Sensitive service
operations should still accept the acting user ID and enforce their required
role, so a newly registered handler cannot accidentally bypass authorization.

For simple commands, use PTB's `CommandHandler.has_args` where it expresses the
contract. Use an explicit parser for optional or structured arguments, and
convert invalid input into command-specific usage responses rather than an
unhandled `IndexError` or `KeyError`.

Use `ConversationHandler` for multi-message operations such as constructing a
phonebook reply or broadcast. Give each workflow explicit entry, content,
confirmation, cancellation, and timeout states. Text-content states must
exclude commands so that a mistyped `/done` is not stored as quest content.
PTB recommends sequential update processing for stateful conversation handlers,
so leave concurrent updates disabled unless the design is changed deliberately:
[PTB concurrency guidance](https://docs.python-telegram-bot.org/en/latest/telegram.ext.applicationbuilder.html#telegram.ext.ApplicationBuilder.concurrent_updates),
[ConversationHandler documentation](https://docs.python-telegram-bot.org/en/latest/telegram.ext.conversationhandler.html).

## Service and behavior design

Handlers should be thin, but the service should remain concrete and readable.
Useful service operations might be:

```python
await service.perform_call(captain_id, update_id, number, password, deliver)
service.get_status(captain_id)
service.set_calls_paused(admin_id, paused=True)
service.save_phone_reply(admin_id, phone, password, parts)
await service.run_broadcast(admin_id, parts, deliver_to_captain)
```

`perform_call` should own the participant-favouring ordering: look up the
reply, deliver it, and only then record the deducted point. Passing a delivery
port or callback lets this policy remain in one operation without importing PTB
types into the service.

Define a few intentional application errors—such as `UsageError`,
`NotAuthorized`, `CallsPaused`, and `UnknownUser`—and map them to Telegram
messages at the adapter boundary. Unexpected exceptions should be logged with
`update_id`, user ID, command, and a traceback, then produce the generic user
message.

Allow commands in any chat where Telegram delivers them to the bot. If group
use is enabled, scope conversational state by both user and chat so an admin
cannot start an operation in one chat and accidentally continue it in another.

Use UTC without conversion for stored timestamps, calculations, reports, and
display. Label displayed clocks as UTC where ambiguity is possible. Keep the
database insertion time separately from Telegram's message time when incident
reconstruction matters.

## Storage design

SQLite remains a reasonable default for one bot process and short
transactions. Start with one explicitly owned connection rather than four
module-level connections. PTB processes updates one at a time unless concurrency
is enabled, which fits this model and stateful admin conversations.

The store should:

- open only during application startup and close during shutdown;
- run versioned migrations before polling starts;
- use a transaction scope around every write operation;
- enable foreign keys and configure a bounded busy timeout explicitly;
- consider WAL mode for reader/writer overlap, while remembering there is still
  only one SQLite writer;
- avoid process-wide caches unless measurement shows they are needed; and
- log database errors together with transaction context and `in_transaction`
  state before rolling back.

Design these invariants into the initial schema:

- a unique `update_id` on point-deducting call records;
- `CHECK` constraints for roles and reply types;
- non-null reply ordering and data fields;
- a real singleton invariant for global quest state;
- broadcast and recipient status if interrupted broadcasts must be resumable;
  and
- an explicit schema-version table.

If a managed PostgreSQL or MySQL service is already reliable and available, it
can provide better write-lock fault isolation and operational diagnostics.
Changing databases does not remove the need for short transactions, rollback,
pool limits, idempotency, and single-instance control. Keep database-specific
code behind `QuestStore` so this decision does not affect handlers.

## Preferred testing approach

Use Application E2E tests as the primary suite, continuing the approach proven
in this repository:

- instantiate the real PTB `Application` and all production handlers;
- use the real service, migrations, SQL, and a temporary file-backed SQLite
  database;
- construct Telegram-shaped updates and pass them through
  `Application.process_update()`;
- fake only PTB's external `BaseRequest` boundary; and
- assert outgoing Telegram operations and later user-visible commands such as
  `/status`, `/progress`, or `/leaderboard`.

The new lifecycle removes the current dynamic-import workaround. A fixture can
own everything normally:

```python
import pytest_asyncio


@pytest_asyncio.fixture
async def bot_harness(tmp_path):
    with SqliteQuestStore(tmp_path / "quest.db") as store:
        store.migrate()
        seed_quest(store)
        fake_telegram = FakeTelegramRequest()
        service = QuestService(store)
        application = create_application(
            test_settings(),
            service,
            request=fake_telegram,
        )

        async with application:
            yield TelegramHarness(application, fake_telegram)
```

Keep `FakeTelegramRequest`, `TelegramUser`, update builders, and the outbound
message timeline under `tests/support/telegram.py`. Extend the fake only when a
scenario requires a new Bot API method or error. PTB provides the public
application lifecycle and request-injection seams, although it does not ship a
complete fake Telegram server:
[Application documentation](https://docs.python-telegram-bot.org/en/latest/telegram.ext.application.html),
[ApplicationBuilder request injection](https://docs.python-telegram-bot.org/en/latest/telegram.ext.applicationbuilder.html#telegram.ext.ApplicationBuilder.request).

Direct database setup is acceptable for initial administrators and quest
fixtures. Test behavior and persistence effects through user-facing operations
where practical. Add lower-level unit tests only when a pure algorithm becomes
complicated enough that E2E scenarios are awkward; do not create service and
repository test suites merely to satisfy a testing pyramid.

Start with these scenarios:

1. Successful and unsuccessful captain calls followed by `/status`.
2. Paused, unauthorized, and malformed calls.
3. Delivery failure does not deduct a point.
4. Duplicate `update_id` does not deduct twice.
5. Complete admin creation of a phonebook reply through a conversation.
6. Broadcast success, partial failure, completion, and retry behavior.
7. Progress ordering and timestamp formatting in UTC.

## Type-checking policy

Annotate both `src/` and `tests/`, including fixtures and the fake Telegram
transport. This catches mismatched PTB callback and `BaseRequest` signatures in
the same way as production interface mistakes. Prefer concrete domain types,
dataclasses, enums, and a small `QuestStore` protocol over unstructured
dictionaries passed between layers.

Start with mypy's `strict = true`. It is strict enough to require annotations,
check untyped calls, reject accidental `Any` propagation in many common places,
and report stale ignores, without enabling the especially noisy
`disallow_any_expr`. Add `warn_unreachable` as a useful extra. Do not enable a
global `ignore_missing_imports`; if a dependency genuinely has no type
information, add a narrow, documented per-module override instead.

Every `# type: ignore` should include the specific error code and a reason when
the reason is not obvious:

```python
value = library_call()  # type: ignore[no-untyped-call]  # Library has no stubs.
```

With the source package installed by `uv sync`, mypy can check normal package
imports without `MYPYPATH` or modifications to `sys.path`. Keep the checked
paths in `pyproject.toml` so local and CI invocations are identical. Mypy reads
its `[tool.mypy]` configuration directly from that file:
[mypy configuration documentation](https://mypy.readthedocs.io/en/stable/config_file.html#using-a-pyproject-toml-file).

## uv project specification

Use a packaged application with a `src` layout and console entry point. With a
current uv, initialize it explicitly so the intended layout does not depend on
the defaults of a particular uv release:

```bash
uv init --app --package --python 3.12 next-quest-bot
cd next-quest-bot
uv add "python-telegram-bot>=22.8,<23" python-dotenv
uv add --dev mypy pre-commit pytest pytest-asyncio ruff
uv sync
```

Python 3.12 is a conservative minimum for a new deployment; select a newer
minimum only after confirming the target server. Recheck dependency ranges
when the project is actually created rather than copying these example bounds
indefinitely.

Use standard project metadata and standardized dependency groups instead of
`requirements.txt` and `requirements-dev.txt`. An illustrative
`pyproject.toml` is:

```toml
[project]
name = "next-quest-bot"
version = "0.1.0"
description = "Telegram bot for an online quest"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "python-dotenv>=1,<2",
    "python-telegram-bot>=22.8,<23",
]

[project.scripts]
next-quest-bot = "quest_bot.__main__:main"

[dependency-groups]
dev = [
    "mypy",
    "pre-commit",
    "pytest",
    "pytest-asyncio",
    "ruff",
]

[tool.mypy]
python_version = "3.12"
files = ["src", "tests"]
strict = true
warn_unreachable = true
pretty = true
show_error_codes = true

[tool.pytest.ini_options]
asyncio_mode = "strict"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

# Let the installed `uv init` generate and maintain a compatible uv_build range.
[build-system]
requires = ["uv_build>=0.12.1,<0.13"]
build-backend = "uv_build"
```

The current uv project workflow uses `[project].dependencies` for runtime
packages and the standardized `[dependency-groups]` table for local development
tools. The `dev` group is included by default during `uv sync` and `uv run`:
[uv dependency documentation](https://docs.astral.sh/uv/concepts/projects/dependencies/).

Commit `pyproject.toml`, `.python-version`, and `uv.lock`. Do not edit
`uv.lock` manually. uv creates and updates it during project operations, and it
should be committed to make installations reproducible:
[uv project layout and lockfile documentation](https://docs.astral.sh/uv/concepts/projects/layout/).

Normal commands then become:

```bash
uv sync                         # create/update .venv from pyproject and uv.lock
uv run next-quest-bot           # run the console entry point
uv run pytest                   # run tests with the default dev group
uv run ruff check .             # lint
uv run ruff format --check .    # verify formatting
uv run mypy                     # check src/ and tests/ from pyproject config
uv lock --check                 # verify that pyproject and lockfile agree
uv run pre-commit install       # install this repository's commit hook once
uv run pre-commit run --all-files  # run the complete commit suite manually
```

For deployment, use locked resolution and exclude development tools, for
example `uv sync --locked --no-dev`. Requirements files should be exported only
when an external deployment system requires them. Current uv application
templates use a build system, `src` layout, and console script specifically to
avoid import-path ambiguity and support installed commands:
[uv application initialization](https://docs.astral.sh/uv/concepts/projects/init/).

## Commit hook

Commit `.pre-commit-config.yaml` so the project defines one local check suite.
After the first `uv sync`, each developer installs it once with
`uv run pre-commit install`. The hook should run all checks on every commit,
including documentation-only commits; the bot is small enough that consistency
is more valuable than trying to select checks from the changed filenames.

```yaml
repos:
  - repo: local
    hooks:
      - id: uv-lock
        name: Verify uv lockfile
        entry: uv lock --check
        language: system
        pass_filenames: false
        always_run: true

      - id: ruff-format
        name: Check formatting
        entry: uv run --locked ruff format --check .
        language: system
        pass_filenames: false
        always_run: true

      - id: ruff-check
        name: Lint
        entry: uv run --locked ruff check .
        language: system
        pass_filenames: false
        always_run: true

      - id: mypy
        name: Type-check
        entry: uv run --locked mypy
        language: system
        pass_filenames: false
        always_run: true

      - id: pytest
        name: Test
        entry: uv run --locked pytest
        language: system
        pass_filenames: false
        always_run: true
```

`pass_filenames: false` matters because each command checks the complete
project, rather than accepting only the files staged for this commit.
`always_run: true` makes that intent explicit even for commits containing no
Python files. The commands use `--locked`, so a check cannot silently rewrite
the dependency resolution. The separate first hook produces a direct error
when `pyproject.toml` and `uv.lock` disagree.

The configuration is versioned, but Git's generated `.git/hooks/pre-commit`
file is local and cannot be installed merely by cloning a repository. Put the
installation command in `README.md` and `CONTRIBUTING.md` if the latter is
added. A developer can also bypass a hook with `git commit --no-verify`, so CI
remains the authoritative check for contributions and the post-push check for
direct commits to `main`. The official uv guide describes using uv-managed
tools from pre-commit:
[uv and pre-commit](https://docs.astral.sh/uv/guides/integration/pre-commit/).

## GitHub Actions

Add `.github/workflows/checks.yml` when the project is created. Trigger it for
every push to `main` and every pull request. Do not add a PR branch filter: a
contributor may open a PR against a branch other than `main`, and the checks are
still useful. Do not use path filters either, because they can leave a required
check permanently waiting on documentation-only PRs.

The checks do not need repository secrets or write access. Use the
`pull_request` event—not `pull_request_target`—and give the token read-only
content permission so PRs from forks can be checked safely. GitHub may still
require manual approval before a first-time fork contributor's workflow runs,
depending on repository settings.

An initial workflow is:

```yaml
name: Checks

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: checks-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  checks:
    name: Project checks
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Check out the repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Install uv
        uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          version: "0.12.1"
          enable-cache: true

      - name: Install Python
        run: uv python install

      - name: Install locked dependencies
        run: uv sync --locked

      - name: Run commit checks
        run: uv run --no-sync pre-commit run --all-files --show-diff-on-failure
```

Calling pre-commit here is deliberate: local commits and CI execute the same
lockfile, Ruff, mypy, and pytest definitions. `uv sync --locked` is still a
separate environment-setup step; it also fails early if the committed lockfile
is stale.

Pin third-party actions to full commit hashes, with the corresponding release
in a comment, and update those pins deliberately or through Dependabot. The
current uv GitHub Actions guide recommends `astral-sh/setup-uv` and provides the
current action pins:
[uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).

The workflow makes failures visible but does not by itself prevent a merge.
For outside contributions, merge a PR only after `Project checks`
passes. A strict required-check rule can prevent a new direct push because that
commit has no remote check result yet. Since the maintainer intentionally works
directly on `main`, either give the maintainer bypass permission in the branch
ruleset or treat the local hook plus the post-push workflow as the maintainer
path while requiring checks for contributor PRs. Do not accidentally configure
a PR-only rule that makes the intended direct-commit workflow impossible.

The push workflow verifies the resulting head of `main`, while the PR workflow
verifies every new PR commit. The concurrency group cancels obsolete runs for
the same branch or PR so the newest commit is the one that continues running.
GitHub documents required checks and their latest-commit behavior here:
[protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[required-check troubleshooting](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks).

Put a linked status badge immediately below the title in `README.md`, using the
real repository owner and name:

```markdown
[![Checks](https://github.com/OWNER/REPOSITORY/actions/workflows/checks.yml/badge.svg?branch=main&event=push)](https://github.com/OWNER/REPOSITORY/actions/workflows/checks.yml)
```

Specifying both `branch=main` and `event=push` makes the badge report the health
of the deployed development line, rather than whichever PR happened to run
most recently. Link the badge to the workflow so a failure is one click away.
GitHub documents the badge URL and filters here:
[workflow status badges](https://docs.github.com/en/actions/how-tos/monitor-workflows/add-a-status-badge).

## Additional implementation improvements

- Use one HTML or carefully wrapped Markdown rendering module; never interpolate
  arbitrary database values directly into MarkdownV2.
- Store command argument parsing in small typed functions so handlers have one
  success path and one usage-error path.
- Avoid `Any` in internal models and services; confine it to unavoidable JSON
  and third-party boundaries and narrow it immediately.
- Keep application logs distinct from the database call/audit history.
- Log startup facts useful during an incident: application version, schema
  version, database path, and whether calls start paused. Never log the bot
  token.
- Persist broadcast recipient progress if an interrupted broadcast must be
  resumed without duplicate deliveries.
- Decide explicitly whether admin conversation drafts may be lost on restart;
  persist them only if that operational cost justifies the complexity.
- Document the intended BotFather group setting for the deployment; do not
  duplicate that choice with a handler-level chat restriction.
- Run the exact deployed revision against a copied quest database before the
  event, then rehearse backup, restart, pause/resume, and broadcast procedures.

## Implementation order

1. Create the uv package, settings, explicit store lifecycle, migrations, and
   application factory.
2. Port only `/call` and `/status`; build the E2E harness and cover their main
   success and failure behavior.
3. Add admin modules one workflow at a time, with an E2E scenario added alongside
   each workflow.
4. Add idempotency, consistent UTC timestamps, schema constraints, structured
   errors, and broadcast resumption before loading final quest content.
5. Keep mypy passing as each module is introduced; do not postpone annotations
   until the bot is complete.
6. Add and install the committed pre-commit configuration for the lockfile,
   Ruff, mypy, and pytest.
7. Add GitHub Actions invoking that same suite, put its `main` push badge in
   `README.md`, and configure contributor PR rules without blocking the
   maintainer's direct-to-`main` workflow.
8. Perform an operational rehearsal on the intended host and database.

This order validates the architecture against real bot behavior early, before
the larger admin surface makes structural changes expensive.
