from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, time, date
import os
import pytz
import random
import sqlite3

TOKEN = os.getenv("TOKEN")
tz = pytz.timezone("Europe/Warsaw")

# база
conn = sqlite3.connect("tasks.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    time TEXT,
    done INTEGER DEFAULT 0
)
""")
conn.commit()

keyboard = ReplyKeyboardMarkup(
    [
        ["Add task", "Show tasks"],
        ["Today", "Done"],
        ["Delete task"]
    ],
    resize_keyboard=True
)

motivation = [
    "Nice job 💪",
    "You’re doing great 🔥",
    "Keep going 🚀",
    "Proud of you ❤️"
]

def format_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

# 🔥 ВОССТАНОВЛЕНИЕ НАПОМИНАНИЙ
async def restore_jobs(app):
    cursor.execute("SELECT id, user_id, text, time FROM tasks WHERE done = 0")
    rows = cursor.fetchall()

    for r in rows:
        task_time = datetime.fromisoformat(r[3])
        task_time = tz.localize(task_time) if task_time.tzinfo is None else task_time

        delay = (task_time - datetime.now(tz)).total_seconds()

        if delay > 0:
            app.job_queue.run_once(
                send_reminder,
                when=delay,
                data={"chat_id": r[1], "text": r[2], "id": r[0]}
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    context.job_queue.run_daily(
        send_daily_plan,
        time=time(hour=8, minute=0, tzinfo=tz),
        data={"chat_id": update.effective_chat.id, "user_id": user_id}
    )

    await update.message.reply_text(
        "Hi! I'm your task diary bot 📓",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ADD
    if text == "Add task":
        await update.message.reply_text("Task | YYYY-MM-DD HH:MM")
        return

    # SHOW ALL
    if text == "Show tasks":
        cursor.execute("""
        SELECT id, text, time, done FROM tasks 
        WHERE user_id = ? ORDER BY time
        """, (user_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = ""
        for r in rows:
            t = datetime.fromisoformat(r[2])
            status = "✅" if r[3] else "⏳"
            msg += f"{r[0]}. {r[1]} — {format_time(t)} {status}\n"

        await update.message.reply_text(msg)
        return

    # TODAY
    if text == "Today":
        today = date.today()

        cursor.execute("""
        SELECT id, text, time FROM tasks 
        WHERE user_id = ? AND done = 0
        """, (user_id,))
        rows = cursor.fetchall()

        msg = "📅 Today:\n\n"
        found = False

        for r in rows:
            t = datetime.fromisoformat(r[2])
            if t.date() == today:
                msg += f"{r[0]}. {r[1]} ({t.strftime('%H:%M')})\n"
                found = True

        if not found:
            msg = "No tasks today ✨"

        await update.message.reply_text(msg)
        return

    # DELETE
    if text == "Delete task":
        await update.message.reply_text("Send ID to delete")
        context.user_data["mode"] = "delete"
        return

    # DONE
    if text == "Done":
        await update.message.reply_text("Send ID completed")
        context.user_data["mode"] = "done"
        return

    # обработка ID
    if context.user_data.get("mode") in ["delete", "done"]:
        try:
            task_id = int(text)

            if context.user_data["mode"] == "delete":
                cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                await update.message.reply_text("Deleted ❌")

            else:
                cursor.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
                conn.commit()
                await update.message.reply_text(random.choice(motivation))

            context.user_data["mode"] = None

        except:
            await update.message.reply_text("Invalid ID")
        return

    # ADD TASK
    if "|" in text:
        try:
            task_text, task_time = text.split("|")
            task_time = tz.localize(datetime.strptime(task_time.strip(), "%Y-%m-%d %H:%M"))

            cursor.execute(
                "INSERT INTO tasks (user_id, text, time) VALUES (?, ?, ?)",
                (user_id, task_text.strip(), task_time.isoformat())
            )
            conn.commit()

            task_id = cursor.lastrowid

            delay = (task_time - datetime.now(tz)).total_seconds()

            if delay > 0:
                context.job_queue.run_once(
                    send_reminder,
                    when=delay,
                    data={"chat_id": update.effective_chat.id, "text": task_text, "id": task_id}
                )

            await update.message.reply_text(f"Added (ID: {task_id})")

        except:
            await update.message.reply_text("Wrong format")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        job.data["chat_id"],
        f"⏰ Task #{job.data['id']}: {job.data['text']}"
    )

async def send_daily_plan(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    chat_id = context.job.data["chat_id"]

    cursor.execute("""
    SELECT id, text, time FROM tasks 
    WHERE user_id = ? AND done = 0 ORDER BY time
    """, (user_id,))
    rows = cursor.fetchall()

    if not rows:
        await context.bot.send_message(chat_id, "No tasks for today ✨")
        return

    msg = "🌅 Today plan:\n\n"

    for r in rows:
        t = datetime.fromisoformat(r[2])
        msg += f"{r[0]}. {r[1]} ({t.strftime('%H:%M')})\n"

    await context.bot.send_message(chat_id, msg)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# 🔥 запуск восстановления
app.post_init = restore_jobs

app.run_polling()
