import logging
import os

from typing import Optional
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

load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# The [ExtBot, dict, ChatData, dict] is for type checkers like mypy
class GameContext: #CustomContext(CallbackContext[ExtBot, dict, ChatData, dict]):
    LOCS = {"Seattle" : "Привіт ти зустрів Олексія і його дивного друга",
            "Graz" : "Олена Василіївна розповіла дивовижну історію, що її онук викопав останки динозавра",
            "Kyiv" : "Олександр Крижановський знов дав самостійну роботу",
            }
    APPS = {"Seattle" : "Seattle_friend.jpg",
            "Graz" : "Graz_grand.mp4",
            }
    """Custom class for context."""
    def __init__(
        self,
    ):
        self._visits = 0
        self._action = 0

    @property
    def visits(self) -> int:
        return self._visits

    def add_visit(self):
        self._visits += 1


    @property
    def action(self) -> int:
        return self._action

    @action.setter
    def action(self, value : int):
        self._action = value

    def check_location(self, location: str) -> Optional[str]:
        if (location in self.LOCS):
            return self.LOCS[location]
        return None

    def check_app(self, location: str) -> Optional[str]:
        if (location in self.APPS):
            return self.APPS[location]
        return None

def get_game_context(context: ContextTypes.DEFAULT_TYPE) -> Optional[GameContext]:
    if (context.user_data is None or "game_context" not in context.user_data):
        return None
    return context.user_data["game_context"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (context.user_data is None):
        context.user_data = {}
    if ("game_context" not in context.user_data):
        context.user_data["game_context"] = GameContext()
    if (update.message is not None):
        await update.message.reply_text("You can /visit to a location or call a number. Use /status to see how many visits and calls you have made.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_context = get_game_context(context)
    if (update.message is None):
        return
    if game_context is None:
        await update.message.reply_text("Please use /start to start a game")
        return
    await update.message.reply_text("you have done {} visits, 0 calls".format(game_context.visits))

async def visit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_context = get_game_context(context)
    if (update.message is None):
        return
    if game_context is None:
        await update.message.reply_text("Please use /start to start a game")
        return
    game_context.action = 1
    await update.message.reply_text("Please enter the place you want to visit.")

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_context = get_game_context(context)
    if (update.message is None):
        return
    if game_context is None:
        await update.message.reply_text("Please use /start to start a game")
        return
    if (game_context.action != 1):
        await update.message.reply_text("Please select an action.")
        return
    if (update.message.text is not None):
        message = update.message.text
    if (message == "Clear"):
        game_context.action = 0
        await update.message.reply_text("Try another action.")
        return
    reply = game_context.check_location(message)
    if (reply is not None):
        await update.message.reply_text(reply)
        game_context.action = 0
        game_context.add_visit()
        pic = game_context.check_app(message)
        if (pic is not None):
            await context.bot.send_document(chat_id = update.message.chat_id,document = open(pic,"rb"))
        return
    await update.message.reply_text("This location is not found, try other place!")

async def sticker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.sticker is None:
        return
    file_id = escape_markdown(update.message.sticker.file_id, version=2)
    await update.message.reply_text(f"Sticker ID: `{file_id}`", parse_mode="MarkdownV2")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    file_id = escape_markdown(update.message.photo[0].file_id, version=2)
    await update.message.reply_text(f"Photo ID: `{file_id}`", parse_mode="MarkdownV2")

async def call(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args is None or update.message is None:
        return
    number = context.args[0]
    password = context.args[1] if 1 < len(context.args) else None
    if number == "18824" and password is None:
        await update.message.reply_text("""Слухайте, його вбили! Мого нареченого, мого Вольдемара! Він був такий красунчик, навіть величезна родимка під лівим оком його не псувала. А я так мріяла стати місіс Хайр! О ні, я ніяк не можу в це повірити!""")
        await update.message.reply_photo("AgACAgIAAxkBAAM_aIokSPLIXskc7hZRtHQgzdZPnnoAAjYdMhtOuVFIM2ToiobwfqUBAAMCAANzAAM2BA")
    else:
        await update.message.reply_text("_Ніхто не відповідає\\.\\.\\._",
                                        parse_mode="MarkdownV2")

def main() -> None:
    token = os.getenv("TOKEN")
    if token is None:
        print("TOKEN is not in the environment")
        return
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("visit", visit))
    application.add_handler(CommandHandler("call", call))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    application.add_handler(MessageHandler(filters.Sticker.ALL, sticker_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
