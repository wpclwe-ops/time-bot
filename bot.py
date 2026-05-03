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
    done INTEGER DEFAULT 0
)
""")
conn.commit()

main_keyboard = ReplyKeyboardMarkup(
    [["Add", "Edit"],
     ["Tasks", "Today"],
     ["Delete", "Done"]],
    resize_keyboard=True
)

tasks_keyboard = ReplyKeyboardMarkup(
    [["All tasks", "My tasks"],
     ["Rita tasks", "Callum tasks"],
     ["Back"]],
    resize_keyboard=True
)

today_keyboard = ReplyKeyboardMarkup(
    [["All today", "Rita today"],
     ["Callum today", "Back"]],
    resize_keyboard=True
)

def build_task_keyboard(rows, context):
    buttons = []
    context.user_data["task_map"] = {}

    for r in rows:
        label = f"{r[0]} — {r[1][:20]}"
        buttons.append([label])
        context.user_data["task_map"][label] = r[0]

    buttons.append(["Back to menu"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

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
    await update.message.reply_text(
        "Hi! I’m your shared planner 💖\n"
        "I’ll help you not forget important things 🥰\n\n"
        "Let’s plan something together ✨",
        reply_markup=main_keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # GLOBAL BACK
    if text == "Back to menu":
        context.user_data["mode"] = None
        await update.message.reply_text("Main menu", reply_markup=main_keyboard)
        return

    if text == "Tasks":
        await update.message.reply_text("Choose:", reply_markup=tasks_keyboard)
        return

    if text == "Today":
        await update.message.reply_text("Choose:", reply_markup=today_keyboard)
        return

    if text == "Back":
        await update.message.reply_text("Main menu", reply_markup=main_keyboard)
        return

    if text == "Add":
        await update.message.reply_text(f"Task | YYYY-MM-DD HH:MM | {MY_NAME}/{PARTNER_NAME}")
        return

    # DELETE
    if text == "Delete":
        cursor.execute("SELECT id, text FROM tasks WHERE done=0 ORDER BY time")
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        context.user_data["mode"] = "delete_buttons"
        await update.message.reply_text(
            "Choose task to delete:",
            reply_markup=build_task_keyboard(rows, context)
        )
        return

    # EDIT
    if text == "Edit":
        cursor.execute("SELECT id, text FROM tasks WHERE done=0 ORDER BY time")
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        context.user_data["mode"] = "edit_select"
        await update.message.reply_text(
            "Choose task to edit:",
            reply_markup=build_task_keyboard(rows, context)
        )
        return

    # DONE (КНОПКИ)
    if text == "Done":
        cursor.execute("SELECT id, text FROM tasks WHERE done=0 ORDER BY time")
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        context.user_data["mode"] = "done_buttons"
        await update.message.reply_text(
            "Mark tasks as done:",
            reply_markup=build_task_keyboard(rows, context)
        )
        return

    # ===== TASK LIST =====

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

    # ===== TODAY =====

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

    # ===== MODES =====

    if context.user_data.get("mode") == "delete_buttons":
        task_map = context.user_data.get("task_map", {})

        if text in task_map:
            task_id = task_map[text]
            cursor.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
            conn.commit()
            await update.message.reply_text("Deleted ❌", reply_markup=main_keyboard)
            context.user_data["mode"] = None
        else:
            await update.message.reply_text("Invalid choice")
        return

    if context.user_data.get("mode") == "done_buttons":
        task_map = context.user_data.get("task_map", {})

        if text in task_map:
            task_id = task_map[text]
            cursor.execute("UPDATE tasks SET done=1 WHERE id=%s", (task_id,))
            conn.commit()
            await update.message.reply_text(random.choice(motivation))
            # остаёмся в режиме — можно нажимать ещё
        else:
            await update.message.reply_text("Invalid choice")
        return

    if context.user_data.get("mode") == "edit_select":
        task_map = context.user_data.get("task_map", {})

        if text in task_map:
            context.user_data["edit_id"] = task_map[text]
            context.user_data["mode"] = "edit"
            await update.message.reply_text(
                "Send: text | YYYY-MM-DD HH:MM",
                reply_markup=main_keyboard
            )
        else:
            await update.message.reply_text("Invalid choice")
        return

    if context.user_data.get("mode") == "edit":
        try:
            task_id = context.user_data.get("edit_id")
            new_text, new_time = text.split("|")
            new_time = tz.localize(datetime.strptime(new_time.strip(), "%Y-%m-%d %H:%M"))

            cursor.execute(
                "UPDATE tasks SET text=%s, time=%s WHERE id=%s",
                (new_text.strip(), new_time.isoformat(), task_id)
            )
            conn.commit()
            await update.message.reply_text("Updated ✏️")
            context.user_data["mode"] = None

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        return

    # ===== ADD =====

    if "tomorrow" in text.lower():
        text = text.replace(
            "tomorrow",
            (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        )

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

            await update.message.reply_text(f"Added (ID: {task_id})")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
