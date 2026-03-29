from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import pytz
import os
import time

TOKEN = os.getenv("TOKEN")

melbourne_tz = pytz.timezone("Australia/Melbourne")
wroclaw_tz = pytz.timezone("Europe/Warsaw")

keyboard = ReplyKeyboardMarkup(
    [["Show time"]],
    resize_keyboard=True
)

def format_time(dt):
    return dt.strftime("%A %d %B %H:%M")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm a bot that shows you the current time 🌍\n"
        "Press the button below to see it 👇",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Show time":
        return

    # анти-дубль
    now = time.time()
    last = context.chat_data.get("last_click", 0)
    if now - last < 1:
        return
    context.chat_data["last_click"] = now

    mel = format_time(datetime.now(melbourne_tz))
    wro = format_time(datetime.now(wroclaw_tz))

    await update.message.reply_text(
        f"🇵🇱 Wroclaw — {wro}\n🇦🇺 Melbourne — {mel}"
    )

    # показываем 1 раз на чат
    if not context.chat_data.get("shown_love"):
        await update.message.reply_text(
            "||P.S. I love you||",
            parse_mode="MarkdownV2"
        )
        context.chat_data["shown_love"] = True


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle_message))

app.run_polling()
