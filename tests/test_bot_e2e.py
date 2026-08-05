import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from telegram import Update
from telegram.request import BaseRequest, RequestData


class FakeTelegramRequest(BaseRequest):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_message_id = 100
        self._bot_user = {
            "id": 999_001,
            "is_bot": True,
            "first_name": "Quest test bot",
            "username": "quest_test_bot",
        }

    @property
    def read_timeout(self) -> float | None:
        return None

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: RequestData | None = None,
        read_timeout: Any = BaseRequest.DEFAULT_NONE,
        write_timeout: Any = BaseRequest.DEFAULT_NONE,
        connect_timeout: Any = BaseRequest.DEFAULT_NONE,
        pool_timeout: Any = BaseRequest.DEFAULT_NONE,
    ) -> tuple[int, bytes]:
        del method, read_timeout, write_timeout, connect_timeout, pool_timeout
        api_method = url.rsplit("/", maxsplit=1)[-1]
        parameters = request_data.parameters if request_data is not None else {}
        self.calls.append((api_method, parameters))

        if api_method == "getMe":
            result = self._bot_user
        elif api_method == "sendMessage":
            self._next_message_id += 1
            result = {
                "message_id": self._next_message_id,
                "date": 1_754_000_000,
                "chat": {
                    "id": parameters["chat_id"],
                    "type": "private",
                },
                "from": self._bot_user,
                "text": parameters["text"],
            }
        else:
            raise AssertionError(f"Unexpected Bot API method: {api_method}")

        response = {"ok": True, "result": result}
        return 200, json.dumps(response).encode()

    def messages_to(self, user_id: int) -> list[str]:
        return [
            parameters["text"]
            for method, parameters in self.calls
            if method == "sendMessage" and parameters["chat_id"] == user_id
        ]


class TelegramUser:
    def __init__(self, application: Any, user_id: int, username: str) -> None:
        self.application = application
        self.user_id = user_id
        self.username = username
        self._next_update_id = 1

    async def send(self, text: str) -> None:
        command = text.split(maxsplit=1)[0]
        update = Update.de_json(
            {
                "update_id": self._next_update_id,
                "message": {
                    "message_id": self._next_update_id,
                    "date": 1_754_000_000 + self._next_update_id,
                    "chat": {
                        "id": self.user_id,
                        "type": "private",
                        "first_name": "Test",
                        "username": self.username,
                    },
                    "from": {
                        "id": self.user_id,
                        "is_bot": False,
                        "first_name": "Test",
                        "username": self.username,
                    },
                    "text": text,
                    "entities": [
                        {
                            "type": "bot_command",
                            "offset": 0,
                            "length": len(command),
                        }
                    ],
                },
            },
            self.application.bot,
        )
        self._next_update_id += 1
        await self.application.process_update(update)


@pytest.mark.asyncio
async def test_successful_call_is_visible_in_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captain_id = 123_456
    module_names = ("bot", "phonebook", "users", "stats", "pause")
    monkeypatch.setenv("QUEST_DB_PATH", str(tmp_path / "quest.db"))

    bot = importlib.import_module("bot")
    phonebook = importlib.import_module("phonebook")
    users = importlib.import_module("users")
    stats = importlib.import_module("stats")
    pause = importlib.import_module("pause")

    try:
        users.add_captain(str(captain_id), "test_captain")
        phonebook.add_number(
            "5551234",
            "answer",
            phonebook.Reply(
                [
                    phonebook.ReplyPart(
                        phonebook.ReplyType.TEXT,
                        "Quest unlocked",
                    )
                ]
            ),
        )

        telegram = FakeTelegramRequest()
        application = bot.create_application(
            "999001:test-token",
            request=telegram,
        )

        async with application:
            captain = TelegramUser(
                application,
                captain_id,
                "test_captain",
            )
            await captain.send("/call 5551234 answer")
            await captain.send("/status")

        assert telegram.messages_to(captain_id) == [
            "Quest unlocked",
            r"Кількість дзвінків — 1\.",
        ]
    finally:
        users.users_connection.close()
        phonebook.phonebook_connection.close()
        stats.stats_connection.close()
        pause.pause_connection.close()
        for module_name in module_names:
            sys.modules.pop(module_name, None)
