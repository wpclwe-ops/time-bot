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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Press the button:",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Show time":
        mel = datetime.now(melbourne_tz).strftime("%H:%M")
        wro = datetime.now(wroclaw_tz).strftime("%H:%M")

        await update.message.reply_text(
            f"Melbourne: {mel}\nWroclaw: {wro}"
        )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle_message))

app.run_polling()
