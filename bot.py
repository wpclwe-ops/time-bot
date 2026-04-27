from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import pytz
import os

TOKEN = os.getenv("TOKEN")

# таймзона Польши
warsaw_tz = pytz.timezone("Europe/Warsaw")

# кнопка
keyboard = ReplyKeyboardMarkup(
    [["Check time"]],
    resize_keyboard=True
)

# дата встречи (польское время!)
target_date = warsaw_tz.localize(datetime(2026, 4, 28, 11, 20))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I will help you find out how many hours are left until you meet your love 💔\n"
        "Press the button below",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Check time":
        return

    # текущее время в Польше
    now = datetime.now(warsaw_tz)

    diff = target_date - now

    # если время уже прошло
    if diff.total_seconds() <= 0:
        await update.message.reply_text("You are already together ❤️")
        return

    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    await update.message.reply_text(
        f"⏳ Time left:\n{days} days {hours} hours {minutes} minutes"
    )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
