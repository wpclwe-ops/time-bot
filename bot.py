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

main_keyboard = ReplyKeyboardMarkup(
    [
        ["Add", "Edit"],
        ["Tasks", "Today"],
        ["Delete", "Done"]
    ],
    resize_keyboard=True
)

tasks_keyboard = ReplyKeyboardMarkup(
    [
        ["All tasks", "My tasks"],
        ["Rita tasks", "Callum tasks"],
        ["Back"]
    ],
    resize_keyboard=True
)

today_keyboard = ReplyKeyboardMarkup(
    [
        ["All today", "Rita today"],
        ["Callum today", "Back"]
    ],
    resize_keyboard=True
)

motivation = [
    "Nice job 💪",
    "You’re doing great 🔥",
    "Keep going 🚀",
    "Proud of you ❤️"
]

def parse_time(db_time):
    t = datetime.fromisoformat(db_time.replace("Z", ""))
    return tz.localize(t) if t.tzinfo is None else t.astimezone(tz)

def format_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Shared planner 💖", reply_markup=main_keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # NAVIGATION
    if text == "Tasks":
        await update.message.reply_text("Choose:", reply_markup=tasks_keyboard)
        return

    if text == "Today":
        await update.message.reply_text("Choose:", reply_markup=today_keyboard)
        return

    if text == "Back":
        await update.message.reply_text("Main menu", reply_markup=main_keyboard)
        return

    # ADD
    if text == "Add":
        await update.message.reply_text(f"Task | YYYY-MM-DD HH:MM | {MY_NAME}/{PARTNER_NAME}")
        return

    # EDIT
    if text == "Edit":
        await update.message.reply_text("ID | new text | YYYY-MM-DD HH:MM")
        context.user_data["mode"] = "edit"
        return

    # DELETE
    if text == "Delete":
        await update.message.reply_text("Send ID or multiple IDs (1,2,3)")
        context.user_data["mode"] = "delete"
        return

    # DONE
    if text == "Done":
        await update.message.reply_text("Send ID or multiple IDs (1,2,3)")
        context.user_data["mode"] = "done"
        return

    # TASK LIST FUNCTION
    async def show_tasks(query, params, title):
        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = f"{title}\n\n"
        for r in rows:
            t = parse_time(r[2])
            status = "✅" if r[3] else "⏳"
            msg += f"{r[0]}. {r[1]} — {format_time(t)} {status}\n"

        await update.message.reply_text(msg)

    # TASKS
    if text == "All tasks":
        await show_tasks("SELECT id,text,time,done FROM tasks ORDER BY time", (), "📋 All")
        return

    if text == "My tasks":
        await show_tasks("SELECT id,text,time,done FROM tasks WHERE user_id=%s ORDER BY time", (user_id,), "📋 My")
        return

    if text == "Rita tasks":
        await show_tasks("SELECT id,text,time,done FROM tasks WHERE user_id=%s", (MY_ID,), "📋 Rita")
        return

    if text == "Callum tasks":
        await show_tasks("SELECT id,text,time,done FROM tasks WHERE user_id=%s", (PARTNER_ID,), "📋 Callum")
        return

    # TODAY
    async def show_today(filter_id=None):
        cursor.execute("SELECT id,text,time,user_id FROM tasks WHERE done=0 ORDER BY time")
        rows = cursor.fetchall()

        msg = "📅 Today:\n\n"
        found = False

        for r in rows:
            t = parse_time(r[2])
            if t.date() == datetime.now(tz).date():
                if filter_id and r[3] != filter_id:
                    continue
                owner = MY_NAME if r[3] == MY_ID else PARTNER_NAME
                msg += f"{r[0]}. {r[1]} ({t.strftime('%H:%M')}) — {owner}\n"
                found = True

        if not found:
            msg = "No tasks today ✨"

        await update.message.reply_text(msg)

    if text == "All today":
        await show_today()
        return

    if text == "Rita today":
        await show_today(MY_ID)
        return

    if text == "Callum today":
        await show_today(PARTNER_ID)
        return

    # MODES
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
                ids = [int(x.strip()) for x in text.split(",")]

                if mode == "delete":
                    for i in ids:
                        cursor.execute("DELETE FROM tasks WHERE id=%s", (i,))
                    conn.commit()
                    await update.message.reply_text(f"Deleted {len(ids)} tasks ❌")

                elif mode == "done":
                    for i in ids:
                        cursor.execute("UPDATE tasks SET done=1 WHERE id=%s", (i,))
                    conn.commit()
                    await update.message.reply_text(random.choice(motivation))

            context.user_data["mode"] = None

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

        return

    # SMART TOMORROW
    if "tomorrow" in text.lower():
        text = text.replace(
            "tomorrow",
            (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        )

    # ADD TASK
    if "|" in text:
        try:
            parts = [p.strip() for p in text.split("|")]

            task_text = parts[0]
            task_time = tz.localize(datetime.strptime(parts[1], "%Y-%m-%d %H:%M"))

            target_user = user_id

            if len(parts) >= 3:
                who = parts[2].lower()
                if who == MY_NAME.lower():
                    target_user = MY_ID
                elif who == PARTNER_NAME.lower():
                    target_user = PARTNER_ID

            cursor.execute(
                "INSERT INTO tasks (user_id, text, time) VALUES (%s, %s, %s) RETURNING id",
                (target_user, task_text, task_time.isoformat())
            )

            task_id = cursor.fetchone()[0]
            conn.commit()

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

            await update.message.reply_text(f"Added (ID: {task_id})")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        job.data["chat_id"],
        f"⏰ Task #{job.data['id']}: {job.data['text']}"
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
