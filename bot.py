from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
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
    repeat TEXT,
    done INTEGER DEFAULT 0
)
""")
cursor.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS repeat TEXT DEFAULT 'none'")
conn.commit()

# ===== HELPERS =====

def format_time(t):
    dt = datetime.fromisoformat(t)
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    label = dt.strftime("%d.%m %H:%M")

    if dt.date() == today:
        label += " (today)"
    elif dt.date() == tomorrow:
        label += " (tomorrow)"

    return label

def get_partner_id(user_id):
    return PARTNER_ID if user_id == MY_ID else MY_ID

# ===== KEYBOARDS =====

main_keyboard = ReplyKeyboardMarkup(
    [["Add", "Edit"],
     ["Tasks", "Today"],
     ["Delete", "Done"]],
    resize_keyboard=True
)

tasks_keyboard = ReplyKeyboardMarkup(
    [["All tasks", "My tasks"],
     ["Partner tasks"],
     ["Back to menu"]],
    resize_keyboard=True
)

today_keyboard = ReplyKeyboardMarkup(
    [["All today", "My today"],
     ["Partner today"],
     ["Back to menu"]],
    resize_keyboard=True
)

user_keyboard = ReplyKeyboardMarkup(
    [[MY_NAME, PARTNER_NAME],
     ["Back to menu"]],
    resize_keyboard=True
)

repeat_keyboard = ReplyKeyboardMarkup(
    [["One-time", "Daily"],
     ["Weekly", "Back to menu"]],
    resize_keyboard=True
)

def build_task_keyboard(rows, context):
    buttons = []
    context.user_data["task_map"] = {}

    for r in rows:
        label = f"{r[1][:25]} — {format_time(r[2])}"
        buttons.append([label])
        context.user_data["task_map"][label] = r[0]

    buttons.append(["Back to menu"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

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

    # ===== ADD FLOW =====

    if text == "Add":
        context.user_data["step"] = "text"
        await update.message.reply_text("📝 Task name?")
        return

    if context.user_data.get("step") == "text":
        context.user_data["task_text"] = text
        context.user_data["step"] = "date"
        await update.message.reply_text("📅 Date (YYYY-MM-DD / today / tomorrow)")
        return

    if context.user_data.get("step") == "date":
        try:
            if text.lower() == "today":
                context.user_data["task_date"] = datetime.now(tz).date()

            elif text.lower() == "tomorrow":
                context.user_data["task_date"] = (datetime.now(tz) + timedelta(days=1)).date()

            else:
                context.user_data["task_date"] = datetime.strptime(text, "%Y-%m-%d").date()

            context.user_data["step"] = "time"
            await update.message.reply_text("⏰ Time (HH:MM)")
        except:
            await update.message.reply_text("Wrong format 😢")
        return

    if context.user_data.get("step") == "time":
        try:
            t = datetime.strptime(text, "%H:%M").time()
            dt = tz.localize(datetime.combine(context.user_data["task_date"], t))
            context.user_data["task_time"] = dt
            context.user_data["step"] = "user"
            await update.message.reply_text("👤 Who?", reply_markup=user_keyboard)
        except:
            await update.message.reply_text("Wrong time 😢")
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
        repeat_map = {
            "One-time": "none",
            "Daily": "daily",
            "Weekly": "weekly"
        }

        if text not in repeat_map:
            return

        repeat = repeat_map[text]

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

        await update.message.reply_text("Added ✨", reply_markup=main_keyboard)
        context.user_data.clear()
        return

    # ===== TASKS =====

    if text == "Tasks":
        await update.message.reply_text("Choose:", reply_markup=tasks_keyboard)
        return

    if text in ["All tasks", "My tasks", "Partner tasks"]:
        if text == "All tasks":
            cursor.execute("SELECT id,text,time FROM tasks")
        elif text == "My tasks":
            cursor.execute("SELECT id,text,time FROM tasks WHERE user_id=%s", (user_id,))
        elif text == "Partner tasks":
            cursor.execute(
                "SELECT id,text,time FROM tasks WHERE user_id=%s",
                (get_partner_id(user_id),)
            )

        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = "📋 Tasks:\n\n"
        for r in rows:
            msg += f"{r[1]} — {format_time(r[2])}\n"

        await update.message.reply_text(msg)
        return

    # ===== TODAY =====

    if text == "Today":
        await update.message.reply_text("Choose:", reply_markup=today_keyboard)
        return

    if "today" in text:
        today = datetime.now(tz).date()
        cursor.execute("SELECT id,text,time,user_id FROM tasks WHERE done=0")
        rows = cursor.fetchall()

        msg = "📅 Today:\n\n"
        found = False

        for r in rows:
            t = datetime.fromisoformat(r[2])
            if t.date() == today:

                if text == "My today" and r[3] != user_id:
                    continue

                if text == "Partner today" and r[3] != get_partner_id(user_id):
                    continue

                msg += f"{r[1]} — {format_time(r[2])}\n"
                found = True

        if not found:
            msg = "No tasks today ✨"

        await update.message.reply_text(msg)
        return

    # ===== DELETE =====

    if text == "Delete":
        cursor.execute("SELECT id,text,time FROM tasks WHERE done=0")
        rows = cursor.fetchall()

        context.user_data["mode"] = "delete"
        await update.message.reply_text(
            "Choose:",
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
        cursor.execute("SELECT id,text,time FROM tasks WHERE done=0")
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
            await update.message.reply_text(random.choice(["Nice 💪", "Good 🔥"]))
        return

# ===== RUN =====

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
