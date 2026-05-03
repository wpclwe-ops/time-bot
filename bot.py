from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta, time
import os
import pytz
import random
import psycopg2

TOKEN = os.getenv("TOKEN")
tz = pytz.timezone("Europe/Warsaw")

MY_ID = 319946231
PARTNER_ID = 8454213226

MY_NAME = "Rita"
PARTNER_NAME = "Callum"

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# ===== TABLE =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    text TEXT,
    time TEXT,
    repeat TEXT,
    done INTEGER DEFAULT 0
)
""")

# 🔥 ВАЖНО — миграция
cursor.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS repeat TEXT DEFAULT 'none'")
conn.commit()

# ===== KEYBOARDS =====

main_keyboard = ReplyKeyboardMarkup(
    [["Add", "Tasks"],
     ["Today", "Done"],
     ["Delete"]],
    resize_keyboard=True
)

user_keyboard = ReplyKeyboardMarkup(
    [[MY_NAME, PARTNER_NAME],
     ["Back to menu"]],
    resize_keyboard=True
)

repeat_keyboard = ReplyKeyboardMarkup(
    [["One-time", "Daily"],
     ["Back to menu"]],
    resize_keyboard=True
)

motivation = [
    "Nice job 💪",
    "You’re doing amazing 🔥",
    "Keep going 🚀",
    "Proud of you ❤️"
]

# ===== REMINDER =====

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data

    await context.bot.send_message(
        data["chat_id"],
        f"⏰ {data['text']} 💖"
    )

    # DAILY ПОВТОР
    if data["repeat"] == "daily":
        new_time = datetime.fromisoformat(data["time"]) + timedelta(days=1)

        cursor.execute(
            "INSERT INTO tasks (user_id, text, time, repeat) VALUES (%s, %s, %s, %s)",
            (data["chat_id"], data["text"], new_time.isoformat(), "daily")
        )
        conn.commit()

        delay = (new_time - datetime.now(tz)).total_seconds()

        if delay > 0:
            context.job_queue.run_once(
                send_reminder,
                when=delay,
                data={
                    "chat_id": data["chat_id"],
                    "text": data["text"],
                    "time": new_time.isoformat(),
                    "repeat": "daily"
                }
            )

# ===== RESTORE =====

async def restore_jobs(app):
    cursor.execute("SELECT user_id, text, time, repeat FROM tasks WHERE done=0")
    rows = cursor.fetchall()

    now = datetime.now(tz)

    for r in rows:
        task_time = datetime.fromisoformat(r[2])
        delay = (task_time - now).total_seconds()

        if delay > 0:
            app.job_queue.run_once(
                send_reminder,
                when=delay,
                data={
                    "chat_id": r[0],
                    "text": r[1],
                    "time": r[2],
                    "repeat": r[3]
                }
            )

# ===== MORNING =====

async def morning_message(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(tz).date()

    cursor.execute("SELECT text, time, user_id FROM tasks WHERE done=0")
    rows = cursor.fetchall()

    for uid in [MY_ID, PARTNER_ID]:
        msg = "🌅 Good morning 💖\n\nToday:\n"
        found = False

        for r in rows:
            t = datetime.fromisoformat(r[1])
            if t.date() == today and r[2] == uid:
                msg += f"• {r[0]} — {t.strftime('%H:%M')}\n"
                found = True

        if found:
            await context.bot.send_message(uid, msg)

# ===== START =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey 💖 I’m your shared planner!\n"
        "I’ll help you not forget important things 🥰",
        reply_markup=main_keyboard
    )

# ===== FLOW =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "Back to menu":
        context.user_data.clear()
        await update.message.reply_text("Back ✨", reply_markup=main_keyboard)
        return

    if text == "Add":
        context.user_data["step"] = "text"
        await update.message.reply_text("📝 Task name?")
        return

    if context.user_data.get("step") == "text":
        context.user_data["task_text"] = text
        context.user_data["step"] = "time"
        await update.message.reply_text("⏰ Date/time: YYYY-MM-DD HH:MM")
        return

    if context.user_data.get("step") == "time":
        try:
            dt = tz.localize(datetime.strptime(text, "%Y-%m-%d %H:%M"))
            context.user_data["task_time"] = dt
            context.user_data["step"] = "user"

            await update.message.reply_text("👤 Who?", reply_markup=user_keyboard)
        except:
            await update.message.reply_text("Wrong format 😢")
        return

    if context.user_data.get("step") == "user":
        if text == MY_NAME:
            context.user_data["target_user"] = MY_ID
        elif text == PARTNER_NAME:
            context.user_data["target_user"] = PARTNER_ID
        else:
            return

        context.user_data["step"] = "repeat"
        await update.message.reply_text("🔁 Repeat?", reply_markup=repeat_keyboard)
        return

    if context.user_data.get("step") == "repeat":
        repeat = "daily" if text == "Daily" else "none"

        task_text = context.user_data["task_text"]
        task_time = context.user_data["task_time"]
        target_user = context.user_data["target_user"]

        cursor.execute(
            "INSERT INTO tasks (user_id, text, time, repeat) VALUES (%s, %s, %s, %s) RETURNING id",
            (target_user, task_text, task_time.isoformat(), repeat)
        )
        task_id = cursor.fetchone()[0]
        conn.commit()

        delay = (task_time - datetime.now(tz)).total_seconds()

        if delay > 0:
            context.job_queue.run_once(
                send_reminder,
                when=delay,
                data={
                    "chat_id": target_user,
                    "text": task_text,
                    "time": task_time.isoformat(),
                    "repeat": repeat
                }
            )

        await update.message.reply_text(f"Added ✨ (ID: {task_id})", reply_markup=main_keyboard)
        context.user_data.clear()
        return

# ===== RUN =====

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.job_queue.run_daily(morning_message, time=time(hour=9, minute=0, tzinfo=tz))

app.post_init = restore_jobs

app.run_polling()
