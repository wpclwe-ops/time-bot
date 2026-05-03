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

# ===== FORMAT TIME =====

def format_time(t):
    dt = datetime.fromisoformat(t)
    return dt.strftime("%d.%m %H:%M")

# ===== KEYBOARDS =====

main_keyboard = ReplyKeyboardMarkup(
    [["Add", "Edit"],
     ["Tasks", "Today"],
     ["Delete", "Done"]],
    resize_keyboard=True
)

tasks_keyboard = ReplyKeyboardMarkup(
    [["All", "My"],
     ["Rita", "Callum"],
     ["Back to menu"]],
    resize_keyboard=True
)

today_keyboard = ReplyKeyboardMarkup(
    [["All today", "My today"],
     ["Rita today", "Callum today"],
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
     ["Back to menu"]],
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

        await update.message.reply_text("Added ✨", reply_markup=main_keyboard)
        context.user_data.clear()
        return

    # TASKS MENU

    if text == "Tasks":
        await update.message.reply_text("Choose:", reply_markup=tasks_keyboard)
        return

    if text in ["All", "My", "Rita", "Callum"]:
        if text == "All":
            cursor.execute("SELECT id,text,time FROM tasks")
        elif text == "My":
            cursor.execute("SELECT id,text,time FROM tasks WHERE user_id=%s", (user_id,))
        elif text == "Rita":
            cursor.execute("SELECT id,text,time FROM tasks WHERE user_id=%s", (MY_ID,))
        elif text == "Callum":
            cursor.execute("SELECT id,text,time FROM tasks WHERE user_id=%s", (PARTNER_ID,))

        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("No tasks")
            return

        msg = "📋 Tasks:\n\n"
        for r in rows:
            msg += f"{r[0]}. {r[1]} — {format_time(r[2])}\n"

        await update.message.reply_text(msg)
        return

    # TODAY

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
                if text == "Rita today" and r[3] != MY_ID:
                    continue
                if text == "Callum today" and r[3] != PARTNER_ID:
                    continue

                msg += f"{r[0]}. {r[1]} — {t.strftime('%H:%M')}\n"
                found = True

        if not found:
            msg = "No tasks today ✨"

        await update.message.reply_text(msg)
        return

    # EDIT

    if text == "Edit":
        cursor.execute("SELECT id,text FROM tasks WHERE done=0")
        rows = cursor.fetchall()

        context.user_data["mode"] = "edit_select"
        await update.message.reply_text(
            "Choose task:",
            reply_markup=build_task_keyboard(rows, context)
        )
        return

    if context.user_data.get("mode") == "edit_select":
        task_map = context.user_data.get("task_map", {})
        if text in task_map:
            context.user_data["edit_id"] = task_map[text]
            context.user_data["mode"] = "edit"
            await update.message.reply_text("Send: text | YYYY-MM-DD HH:MM")
        return

    if context.user_data.get("mode") == "edit":
        try:
            new_text, new_time = text.split("|")
            new_time = tz.localize(datetime.strptime(new_time.strip(), "%Y-%m-%d %H:%M"))

            cursor.execute(
                "UPDATE tasks SET text=%s, time=%s WHERE id=%s",
                (new_text.strip(), new_time.isoformat(), context.user_data["edit_id"])
            )
            conn.commit()

            await update.message.reply_text("Updated ✏️", reply_markup=main_keyboard)
            context.user_data.clear()
        except:
            await update.message.reply_text("Error 😢")
        return

    # DELETE

    if text == "Delete":
        cursor.execute("SELECT id,text FROM tasks WHERE done=0")
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

    # DONE

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
            await update.message.reply_text(random.choice(["Nice 💪", "Good 🔥"]))
        return

# ===== RUN =====

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
