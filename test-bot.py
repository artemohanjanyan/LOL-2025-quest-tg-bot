import logging
import os
from typing import Any, List, Optional
from textwrap import dedent
from enum import Enum

from telegram import (
    Bot,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update
)
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

class Action(Enum):
    ADD_NUMBER = 1
    BROADCAST = 2

class LongActionContext:
    def __init__(self) -> None:
        self._action: Action | None = None
        self._phone: str = ""
        self._password: str | None = None
        self._reply_parts: List[ReplyPart] = []

    def current_action(self) -> Action | None:
        return self._action

    def reply(self) -> Reply:
        return Reply(self._reply_parts)

    def start_add_number(self, phone: str, password: str | None) -> None:
        assert self._action == None, "another operation is in progress"
        self._action = Action.ADD_NUMBER
        self._phone = phone
        self._password = password
        self._reply_parts = []

    def start_broadcast(self) -> None:
        assert self._action == None, "another operation is in progress"
        self._action = Action.BROADCAST
        self._reply_parts = []

    def add_reply_part(self, reply_part: ReplyPart) -> bool:
        if self._action == None:
            return False
        self._reply_parts.append(reply_part)
        return True

    def finish_add_number(self) -> bool:
        if self._action != Action.ADD_NUMBER:
            return False
        phonebook.add_number(self._phone, self._password, Reply(self._reply_parts))
        self._action = None
        return True

    def finish_broadcast(self) -> bool:
        if self._action != Action.BROADCAST:
            return False
        self._action = None
        return True

    def cancel(self) -> bool:
        if self._action == None:
            return False
        self._action = None
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

async def get_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if (update.effective_user is None or
        update.effective_user.id not in users.users):
        await update.message.reply_text("А ви від кого?")
        return
    match users.users[update.effective_user.id]:
        case UserRole.ADMIN:
            await update.message.reply_text(
                dedent("""\
                        /help — показати це повідомлення

                        /call номер [пароль] — зробити дзвінок
                        /status — перевірити кількість дзвінків

                        /add_number номер [пароль] — додати новий номер в телефонну книгу
                        /broadcast — надіслати повідомлення всім користувачам

                        /leaderboard — таблиця лідерів
                        /progress user_id — прогрес окремої команди
                        /add_captain user_id username — додати капітана
                        (user_id треба дізнатись за допомогою @userinfobot)
                        /list_users — показати перелік всіх користувачів

                        /read_users — оновити базу даних користувачів (для Артема)
                        /read_phonebook — оновити телефонну книгу (для Артема)""")
            )
        case UserRole.CAPTAIN:
            await update.message.reply_text(
                dedent("""\
                        /call номер [пароль] — зробити дзвінок
                        /status — перевірити кількість дзвінків
                        """)
            )

#async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#    if update.message is None or update.message.sticker is None:
#        return
#    file_id = escape_markdown(update.message.sticker.file_id, version=2)
#    await update.message.reply_text(f"Sticker ID: `{file_id}`", parse_mode="MarkdownV2")
#
#async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#    if update.message is None:
#        return
#    file_id = escape_markdown(update.message.photo[0].file_id, version=2)
#    await update.message.reply_text(f"Photo ID: `{file_id}`", parse_mode="MarkdownV2")

async def send_reply(message: Message, reply: Reply) -> None:
    for part in reply.parts:
        match part.reply_type:
            case ReplyType.TEXT:
                await message.reply_text(part.reply_data)
            case ReplyType.PHOTO:
                await message.reply_photo(part.reply_data)
            case ReplyType.STICKER:
                await message.reply_sticker(part.reply_data)
            case ReplyType.VOICE:
                await message.reply_voice(part.reply_data)
            case ReplyType.DOCUMENT:
                await message.reply_document(part.reply_data)

async def send_message(bot: Bot, user_id: int, reply: Reply) -> None:
    for part in reply.parts:
        match part.reply_type:
            case ReplyType.TEXT:
                await bot.send_message(user_id, part.reply_data)
            case ReplyType.PHOTO:
                await bot.send_photo(user_id, part.reply_data)
            case ReplyType.STICKER:
                await bot.send_sticker(user_id, part.reply_data)
            case ReplyType.VOICE:
                await bot.send_voice(user_id, part.reply_data)
            case ReplyType.DOCUMENT:
                await bot.send_document(user_id, part.reply_data)

async def call(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_captain_permission(update):
        return
    if (context.args is None or
        update.message is None or
        update.effective_user is None):
        return
    number = context.args[0]
    password = context.args[1] if 1 < len(context.args) else None
    if (number, password) in phonebook.phonebook.replies:
        await send_reply(update.message,
                         phonebook.phonebook.replies[(number, password)])
    else:
        await update.message.reply_text("_Ніхто не відповідає\\.\\.\\._",
                                        parse_mode="MarkdownV2")
    stats.log_call(update.effective_user.id,
                   update.message.date,
                   number,
                   password)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_captain_permission(update):
        return
    if (update.message is None or
        update.effective_user is None):
        return
    call_n = stats.status(update.effective_user.id)
    await update.message.reply_text(f"Кількість дзвінків — {call_n}\\.",
                                    parse_mode="MarkdownV2")

def get_long_action_context(context: ContextTypes.DEFAULT_TYPE) -> LongActionContext:
    if context.user_data is None:
        context.user_data = {}
    if "long_action_context" not in context.user_data:
        context.user_data["long_action_context"] = LongActionContext()
    return context.user_data["long_action_context"]

async def add_number(update: Update,
                     context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if context.args is None or update.message is None:
        return
    long_action_context = get_long_action_context(context)
    if long_action_context.current_action() != None:
        await update.message.reply_text("_Виконується інша операція_",
                                        parse_mode = "MarkdownV2")
        return
    number = context.args[0]
    password = context.args[1] if 1 < len(context.args) else None
    long_action_context.start_add_number(number, password)
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

async def broadcast(update: Update,
                    context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    long_action_context = get_long_action_context(context)
    if long_action_context.current_action() != None:
        await update.message.reply_text("_Виконується інша операція_",
                                        parse_mode = "MarkdownV2")
        return
    long_action_context.start_broadcast()
    await update.message.reply_text(
            dedent(f"""\
                    _Додаємо оголошення для капітанів\\._
                    _Надішліть всі повідомлення оголошення\\._
                    _Після цього підтвердіть оголошення командою_ `/done` _\\._
                    _Для відміни використайте команду_ `/cancel` _\\._
                    """),
            parse_mode = "MarkdownV2"
    )

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    long_action_context = get_long_action_context(context)
    match long_action_context.current_action():
        case None:
            await update.message.reply_text("_Операція не виконується_",
                                            parse_mode = "MarkdownV2")
        case Action.ADD_NUMBER:
            long_action_context.finish_add_number()
            await update.message.reply_text("_Номер додано_",
                                            parse_mode = "MarkdownV2")
        case Action.BROADCAST:
            for user_id, role in users.users.items():
                if role == UserRole.CAPTAIN:
                    await update.message.reply_text(
                            f"_Надсилаю капітану {user_id}_",
                            parse_mode = "MarkdownV2"
                    )
                    await send_message(context.bot,
                                       user_id,
                                       long_action_context.reply())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    long_action_context = get_long_action_context(context)
    if not long_action_context.cancel():
        await update.message.reply_text("_Операція не виконується_",
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

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_admin_permission(update):
        return
    if update.message is None or context.args is None:
        return
    user_id = int(context.args[0])
    result = stats.progress(user_id)
    if result != []:
        await update.message.reply_text(
            "\n".join(map(
                lambda stat: f"{stat[0]} ({stat[1]}) — {stat[2]}",
                result
            ))
        )
    else:
        await update.message.reply_text("Повідомлень поки немає")

async def long_action_handler(update: Update,
                              context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin_permission(update):
        return
    if update.message is None:
        return
    long_action_context = get_long_action_context(context)
    result = False
    if update.message.text is not None:
        result = long_action_context.add_reply_part(
                ReplyPart(ReplyType.TEXT, update.message.text)
        )
    elif update.message.photo is not None and len(update.message.photo) > 0:
        result = long_action_context.add_reply_part(
                ReplyPart(ReplyType.PHOTO, update.message.photo[0].file_id)
        )
    elif update.message.sticker is not None:
        result = long_action_context.add_reply_part(
                ReplyPart(ReplyType.STICKER, update.message.sticker.file_id)
        )
    elif update.message.voice is not None:
        result = long_action_context.add_reply_part(
                ReplyPart(ReplyType.VOICE, update.message.voice.file_id)
        )
    elif update.message.document is not None:
        result = long_action_context.add_reply_part(
                ReplyPart(ReplyType.DOCUMENT, update.message.document.file_id)
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

async def add_captain(update: Update,
                      context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin_permission(update):
        return
    if context.args is None or update.message is None:
        return
    user_id = context.args[0]
    username = context.args[1]
    users.add_captain(user_id, username)

async def list_users(update: Update,
                     context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin_permission(update):
        return
    if context.args is None or update.message is None:
        return
    all_users = users.list_users()
    await update.message.reply_text(
        "\n".join(map(
            lambda user: f"{user[1]} ({user[0]}) — {user[2].value}",
            all_users
        ))
    )

async def error_handler(update: Any | None,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    if update != None and update.message != None:
        await update.message.reply_text("_Технічна помилка_",
                                        parse_mode = "MarkdownV2")

def main() -> None:
    token = os.getenv("TOKEN")
    if token is None:
        print("TOKEN is not in the environment")
        return
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", get_help))

    application.add_handler(CommandHandler("call", call))
    application.add_handler(CommandHandler("status", status))

    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("progress", progress))
    application.add_handler(CommandHandler("read_users", read_users))
    application.add_handler(CommandHandler("read_phonebook", read_phonebook))
    application.add_handler(CommandHandler("add_captain", add_captain))
    application.add_handler(CommandHandler("list_users", list_users))

    application.add_handler(CommandHandler("add_number", add_number))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("done", done))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.TEXT |
                                           filters.PHOTO |
                                           filters.VOICE |
                                           filters.Document.ALL |
                                           filters.Sticker.ALL,
                                           long_action_handler))

    #application.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    #application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
