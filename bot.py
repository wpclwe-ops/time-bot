from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, date, timedelta
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

# 🔥 POSTGRES
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    text TEXT,
    time TEXT,
    done INTEGER DEFAULT 0
)
""")
conn.commit()

keyboard = ReplyKeyboardMarkup(
    [
        ["Add task", "My tasks"],
        ["Callum tasks", "All tasks"],
        ["Today", "Done"],
        ["Delete task", "Edit task"]
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hi! Shared planner 💖\nUse names: {MY_NAME}/{PARTNER_NAME}",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "Add task":
        await update.message.reply_text(
            f"Task | YYYY-MM-DD HH:MM | {MY_NAME}/{PARTNER_NAME} (optional)"
        )
        return

    if text == "My tasks":
        cursor.execute("SELECT id, text, time, done FROM tasks WHERE user_id=%s ORDER BY time", (user_id,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = "📋 My tasks:\n\n"
        for r in rows:
            t = datetime.fromisoformat(r[2])
            status = "✅" if r[3] else "⏳"
            msg += f"{r[0]}. {r[1]} — {format_time(t)} {status}\n"

        await update.message.reply_text(msg)
        return

    if text == "Callum tasks":
        cursor.execute("SELECT id, text, time, done FROM tasks WHERE user_id=%s", (PARTNER_ID,))
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = f"📋 {PARTNER_NAME}'s tasks:\n\n"
        for r in rows:
            t = datetime.fromisoformat(r[2])
            status = "✅" if r[3] else "⏳"
            msg += f"{r[0]}. {r[1]} — {format_time(t)} {status}\n"

        await update.message.reply_text(msg)
        return

    if text == "All tasks":
        cursor.execute("SELECT id, text, time, done, user_id FROM tasks ORDER BY time")
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = "📋 All tasks:\n\n"
        for r in rows:
            t = datetime.fromisoformat(r[2])
            owner = MY_NAME if r[4] == MY_ID else PARTNER_NAME
            status = "✅" if r[3] else "⏳"
            msg += f"{r[0]}. {r[1]} — {format_time(t)}\n👤 {owner} {status}\n\n"

        await update.message.reply_text(msg)
        return

    if text == "Today":
        today = date.today()

        cursor.execute("SELECT id, text, time, user_id FROM tasks WHERE done=0 ORDER BY time")
        rows = cursor.fetchall()

        msg = "📅 Today:\n\n"
        found = False

        for r in rows:
            t = datetime.fromisoformat(r[2])
            if t.date() == today:
                owner = MY_NAME if r[3] == MY_ID else PARTNER_NAME
                msg += f"{r[0]}. {r[1]} ({t.strftime('%H:%M')}) — {owner}\n"
                found = True

        if not found:
            msg = "No tasks today ✨"

        await update.message.reply_text(msg)
        return

    if text == "Delete task":
        await update.message.reply_text("Send ID")
        context.user_data["mode"] = "delete"
        return

    if text == "Done":
        await update.message.reply_text("Send ID")
        context.user_data["mode"] = "done"
        return

    if text == "Edit task":
        await update.message.reply_text("ID | new text | YYYY-MM-DD HH:MM")
        context.user_data["mode"] = "edit"
        return

    if context.user_data.get("mode"):
        try:
            mode = context.user_data["mode"]

            if mode == "edit":
                task_id, new_text, new_time = text.split("|")
                task_id = int(task_id.strip())
                new_time = tz.localize(datetime.strptime(new_time.strip(), "%Y-%m-%d %H:%M"))

                cursor.execute(
                    "UPDATE tasks SET text=%s, time=%s WHERE id=%s",
                    (new_text.strip(), new_time.isoformat(), task_id)
                )
                conn.commit()
                await update.message.reply_text("Updated ✏️")

            else:
                task_id = int(text)

                if mode == "delete":
                    cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
                    conn.commit()
                    await update.message.reply_text("Deleted ❌")

                else:
                    cursor.execute("UPDATE tasks SET done=1 WHERE id=%s", (task_id,))
                    conn.commit()
                    await update.message.reply_text(random.choice(motivation))

            context.user_data["mode"] = None

        except:
            await update.message.reply_text("Error 😢")

        return

    if "tomorrow" in text.lower():
        text = text.replace(
            "tomorrow",
            (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        )

    if "|" in text:
        try:
            parts = text.split("|")

            task_text = parts[0].strip()
            task_time = tz.localize(datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M"))

            target_user = user_id

            if len(parts) >= 3:
                who = parts[2].strip().lower()

                if who == MY_NAME.lower():
                    target_user = MY_ID
                elif who == PARTNER_NAME.lower():
                    target_user = PARTNER_ID

            cursor.execute(
                "INSERT INTO tasks (user_id, text, time) VALUES (%s, %s, %s)",
                (target_user, task_text, task_time.isoformat())
            )
            conn.commit()

            task_id = cursor.fetchone()

            delay = (task_time - datetime.now(tz)).total_seconds()
            sender = MY_NAME if user_id == MY_ID else PARTNER_NAME

            if delay > 0:
                context.job_queue.run_once(
                    send_reminder,
                    when=delay,
                    data={
                        "chat_id": target_user,
                        "text": f"{task_text} (from {sender} 💖)",
                        "id": task_id
                    }
                )

            await update.message.reply_text("Added ✅")

        except:
            await update.message.reply_text("Wrong format 😢")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        job.data["chat_id"],
        f"⏰ {job.data['text']}"
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
