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

def format_time(dt):
    return dt.strftime("%A %d %B %H:%M")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data.clear()

    await update.message.reply_text(
        "Hi! I'm a bot that shows you the current time 🌍\n"
        "Press the button below to see it 👇",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Show time":
        return

    # 🔥 анти-дубль по message_id
    last_id = context.chat_data.get("last_msg_id")
    if last_id == update.message.message_id:
        return
    context.chat_data["last_msg_id"] = update.message.message_id

    mel = format_time(datetime.now(melbourne_tz))
    wro = format_time(datetime.now(wroclaw_tz))

    await update.message.reply_text(
        f"🇵🇱 Wroclaw — {wro}\n🇦🇺 Melbourne — {mel}"
    )

    if not context.chat_data.get("love_shown"):
        await update.message.reply_text(
            "<tg-spoiler>P.S. I love you</tg-spoiler>",
            parse_mode="HTML"
        )
        context.chat_data["love_shown"] = True


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle_message))

app.run_polling()
