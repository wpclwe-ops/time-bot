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

# ===== DB =====
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
cursor.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS repeat TEXT DEFAULT 'none'")
conn.commit()

# ===== KEYBOARDS =====

main_keyboard = ReplyKeyboardMarkup(
    [["Add", "Edit"],
     ["Tasks", "Today"],
     ["Delete", "Done"]],
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

# ===== HELPERS =====

def build_task_keyboard(rows, context):
    buttons = []
    context.user_data["task_map"] = {}

    for r in rows:
        label = f"{r[0]} — {r[1][:20]}"
        buttons.append([label])
        context.user_data["task_map"][label] = r[0]

    buttons.append(["Back to menu"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ===== REMINDER =====

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data

    await context.bot.send_message(
        data["chat_id"],
        f"⏰ {data['text']} ❤️"
    )

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
        msg = "🌅 Good morning ❤️\n\nToday:\n"
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
        "Hi! I’m your shared planner ❤️\n"
        "I’ll help you not forget important things 🥰\n\n"
        "Let’s plan something together ✨",
        reply_markup=main_keyboard
    )

# ===== MAIN =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # BACK
    if text == "Back to menu":
        context.user_data.clear()
        await update.message.reply_text("Back ✨", reply_markup=main_keyboard)
        return

    # ADD FLOW
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

        cursor.execute(
            "INSERT INTO tasks (user_id, text, time, repeat) VALUES (%s, %s, %s, %s)",
            (
                context.user_data["target_user"],
                context.user_data["task_text"],
                context.user_data["task_time"].isoformat(),
                repeat
            )
        )
        conn.commit()

        delay = (context.user_data["task_time"] - datetime.now(tz)).total_seconds()

        if delay > 0:
            context.job_queue.run_once(
                send_reminder,
                when=delay,
                data={
                    "chat_id": context.user_data["target_user"],
                    "text": context.user_data["task_text"],
                    "time": context.user_data["task_time"].isoformat(),
                    "repeat": repeat
                }
            )

        await update.message.reply_text("Added ✨", reply_markup=main_keyboard)
        context.user_data.clear()
        return

    # ===== TASKS =====

    if text == "Tasks":
        cursor.execute("SELECT id,text,time,done FROM tasks ORDER BY time")
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = "📋 Tasks:\n\n"
        for r in rows:
            msg += f"{r[0]}. {r[1]} — {r[2]}\n"

        await update.message.reply_text(msg)
        return

    # ===== DELETE =====

    if text == "Delete":
        cursor.execute("SELECT id,text FROM tasks WHERE done=0")
        rows = cursor.fetchall()

        context.user_data["mode"] = "delete"
        await update.message.reply_text(
            "Choose task:",
            reply_markup=build_task_keyboard(rows, context)
        )
        return

    if context.user_data.get("mode") == "delete":
        task_map = context.user_data.get("task_map", {})

        if text in task_map:
            cursor.execute("DELETE FROM tasks WHERE id=%s", (task_map[text],))
            conn.commit()
            await update.message.reply_text("Deleted ❌", reply_markup=main_keyboard)
            context.user_data.clear()
        return

    # ===== DONE =====

    if text == "Done":
        cursor.execute("SELECT id,text FROM tasks WHERE done=0")
        rows = cursor.fetchall()

        context.user_data["mode"] = "done"
        await update.message.reply_text(
            "Mark done:",
            reply_markup=build_task_keyboard(rows, context)
        )
        return

    if context.user_data.get("mode") == "done":
        task_map = context.user_data.get("task_map", {})

        if text in task_map:
            cursor.execute("UPDATE tasks SET done=1 WHERE id=%s", (task_map[text],))
            conn.commit()
            await update.message.reply_text(random.choice([
                "Nice job 💪",
                "You’re amazing 🔥"
            ]))
        return

# ===== RUN =====

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.job_queue.run_daily(morning_message, time=time(hour=9, minute=0, tzinfo=tz))
app.post_init = restore_jobs

app.run_polling()
