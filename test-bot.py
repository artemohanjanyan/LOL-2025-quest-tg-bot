import logging
import os
from typing import List, Optional
from textwrap import dedent

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ExtBot,
    CallbackContext,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from dotenv import load_dotenv

import phonebook
from phonebook import ReplyPart, ReplyType, Reply

import users
from users import UserRole
import stats

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class AddNumberContext:
    def __init__(
            self,
            ) -> None:
        self._adding: bool = False
        self._phone: str = ""
        self._password: str | None = None
        self._reply_parts: List[ReplyPart] = []

    def start(self, phone: str, password: str | None) -> bool:
        if self._adding:
            return False
        self._adding = True
        self._phone = phone
        self._password = password
        self._reply_parts = []
        return True

    def add_reply_part(self, reply_part: ReplyPart) -> bool:
        if not self._adding:
            return False
        self._reply_parts.append(reply_part)
        return True

    def finish(self) -> bool:
        if not self._adding:
            return False
        phonebook.add_number(self._phone, self._password, Reply(self._reply_parts))
        self._adding = False
        return True

    def cancel(self) -> bool:
        if not self._adding:
            return False
        self._adding = False
        return True

async def check_captain_permission(update: Update) -> bool:
    if (update.effective_user is None or
        update.effective_user.id not in users.users):
        if update.message is not None:
            await update.message.reply_text("А ви від кого?")
        return False
    return True

async def check_admin_permission(update: Update) -> bool:
    if (update.effective_user is None or
        update.effective_user.id not in users.users or
        users.users[update.effective_user.id] != UserRole.ADMIN):
        if update.message is not None:
            await update.message.reply_text("А ви від кого?")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if (context.user_data is None):
        context.user_data = {}

async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.sticker is None:
        return
    file_id = escape_markdown(update.message.sticker.file_id, version=2)
    await update.message.reply_text(f"Sticker ID: `{file_id}`", parse_mode="MarkdownV2")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    file_id = escape_markdown(update.message.photo[0].file_id, version=2)
    await update.message.reply_text(f"Photo ID: `{file_id}`", parse_mode="MarkdownV2")

async def call(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_captain_permission(update):
        return
    if (context.args is None or
        update.message is None or
        update.effective_user is None):
        return
    number = context.args[0]
    password = context.args[1] if 1 < len(context.args) else None
    stats.log_call(update.effective_user.id, update.message.date, number, password)
    if (number, password) in phonebook.phonebook.replies:
        reply = phonebook.phonebook.replies[(number, password)]
        for part in reply.parts:
            match part.reply_type:
                case ReplyType.TEXT:
                    await update.message.reply_text(part.reply_data)
                case ReplyType.PHOTO:
                    await update.message.reply_photo(part.reply_data)
                case ReplyType.STICKER:
                    await update.message.reply_sticker(part.reply_data)
    else:
        await update.message.reply_text("_Ніхто не відповідає\\.\\.\\._",
                                        parse_mode="MarkdownV2")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_captain_permission(update):
        return
    if (update.message is None or
        update.effective_user is None):
        return
    call_n = stats.status(update.effective_user.id)
    await update.message.reply_text(f"Кількість дзвінків — {call_n}\\.",
                                    parse_mode="MarkdownV2")

def get_add_number_context(context: ContextTypes.DEFAULT_TYPE) -> AddNumberContext:
    if context.user_data is None:
        context.user_data = {}
    if "add_number_context" not in context.user_data:
        context.user_data["add_number_context"] = AddNumberContext()
    return context.user_data["add_number_context"]

async def add_number(update: Update,
                     context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if context.args is None or update.message is None:
        return
    add_number_context = get_add_number_context(context)
    number = context.args[0]
    password = context.args[1] if 1 < len(context.args) else None
    if not add_number_context.start(number, password):
        await update.message.reply_text("_Номер вже додається_",
                                        parse_mode = "MarkdownV2")
    else:
        await update.message.reply_text(
                dedent(f"""\
                        _Додаємо номер {number} з паролем {password}\\._
                        _Надішліть всі повідомлення відповіді\\._
                        _Після цього підтвердіть додавання командою_ `/done` _\\._
                        _Для відміни використайте команду_ `/cancel` _\\._
                        _Для видалення одразу надішліть команду_ `/done` _\\._
                        """),
                parse_mode = "MarkdownV2"
        )

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    add_number_context = get_add_number_context(context)
    if not add_number_context.finish():
        await update.message.reply_text("_Номер не додається_",
                                        parse_mode = "MarkdownV2")
    else:
        await update.message.reply_text("_Номер додано_",
                                        parse_mode = "MarkdownV2")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    add_number_context = get_add_number_context(context)
    if not add_number_context.cancel():
        await update.message.reply_text("_Номер не додається_",
                                        parse_mode = "MarkdownV2")
    else:
        await update.message.reply_text("_Відміна_",
                                        parse_mode = "MarkdownV2")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    result = stats.stats()
    await update.message.reply_text(
        "\n".join(map(
            lambda stat: f"{stat[1]} ({stat[2]}) — {stat[0]}",
            result
        ))
    )

async def add_reply_part(update: Update,
                         context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    add_number_context = get_add_number_context(context)
    result = False
    if update.message.text is not None:
        result = add_number_context.add_reply_part(
                ReplyPart(ReplyType.TEXT, update.message.text)
        )
    elif update.message.photo is not None and len(update.message.photo) > 0:
        result = add_number_context.add_reply_part(
                ReplyPart(ReplyType.PHOTO, update.message.photo[0].file_id)
        )
    elif update.message.sticker is not None:
        result = add_number_context.add_reply_part(
                ReplyPart(ReplyType.STICKER, update.message.sticker.file_id)
        )
    if not result:
        await update.message.reply_text("_Повідомлення не додано_",
                                        parse_mode = "MarkdownV2")

async def read_users(update: Update,
                     context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin_permission(update):
        return
    users.read_users()

async def read_phonebook(update: Update,
                         context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin_permission(update):
        return
    phonebook.read_phonebook()

def main() -> None:
    token = os.getenv("TOKEN")
    if token is None:
        print("TOKEN is not in the environment")
        return
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))

    application.add_handler(CommandHandler("call", call))
    application.add_handler(CommandHandler("status", status))

    application.add_handler(CommandHandler("add_number", add_number))
    application.add_handler(CommandHandler("done", done))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("read_users", read_users))
    application.add_handler(CommandHandler("read_phonebook", read_phonebook))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO |
                                           filters.Sticker.ALL, add_reply_part))

    application.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
