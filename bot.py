from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import pytz
import os

TOKEN = os.getenv("TOKEN")

melbourne_tz = pytz.timezone("Australia/Melbourne")
wroclaw_tz = pytz.timezone("Europe/Warsaw")

keyboard = ReplyKeyboardMarkup(
    [["Show time"]],
    resize_keyboard=True
)

# формат даты
def format_time(dt):
    return dt.strftime("%A %d %B %H:%M")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # приветствие
    await update.message.reply_text(
        "Hi! I'm a bot that shows you the current time 🌍\n"
        "Press the button below to see it 👇",
        reply_markup=keyboard
    )

    # скрытое сообщение (spoiler)
    await update.message.reply_text(
        "||I love you||",
        parse_mode="MarkdownV2"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Show time":
        mel = format_time(datetime.now(melbourne_tz))
        wro = format_time(datetime.now(wroclaw_tz))

        await update.message.reply_text(
            f"Wroclaw — {wro}\nMelbourne — {mel}"
        )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle_message))

app.run_polling()
