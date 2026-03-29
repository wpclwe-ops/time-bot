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
    await update.message.reply_text(
        "Hi! I'm a bot that shows you the current time 🌍\n"
        "Press the button below to see it 👇",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Show time":
        mel = format_time(datetime.now(melbourne_tz))
        wro = format_time(datetime.now(wroclaw_tz))

        # отправка времени
        await update.message.reply_text(
            f"🇵🇱 Wroclaw — {wro}\n🇦🇺 Melbourne — {mel}"
        )

        # проверка: показывали ли уже сообщение
        if not context.user_data.get("shown_love"):
            await update.message.reply_text("||I love you||")
            context.user_data["shown_love"] = True

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle_message))

app.run_polling()
