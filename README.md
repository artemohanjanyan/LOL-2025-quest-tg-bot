# Development

## Setup

Create the virtual environment and install the development dependencies. The
development requirements include the runtime requirements as well.

```
uv venv
uv pip install -r requirements-dev.txt
```

## Token

Create `.env` file and put bot token there:

```
TOKEN=1111111111:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

## BotFather configuration

This bot is intended for private chats only. Disable group joining for the bot
through `@BotFather`:

1. Send `/setjoingroups` to `@BotFather`.
2. Select the bot.
3. Choose `Disable`.

This prevents captains from adding the bot to a group where quest replies would
be visible to every member. The setting is stored by Telegram rather than in
this repository, so verify it when configuring a new bot. If the bot is already
present in any groups, remove it from them separately.

## Running

```
uv run python bot.py
```

## Testing

```
uv run pytest
```
