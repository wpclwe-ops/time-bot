from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
import os
import pytz
import random
import psycopg2
import logging

# ===== LOGGING =====
# App logs at DEBUG; httpx/httpcore are suppressed to WARNING to avoid transport-level noise.
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# ===== CONFIG =====
TOKEN = os.getenv("TOKEN")
tz = pytz.timezone("Europe/Warsaw")

MY_ID = 319946231
PARTNER_ID = 8454213226
MY_NAME = "Rita"
PARTNER_NAME = "Callum"
ALLOWED_USERS = {MY_ID, PARTNER_ID}

# ===== DATABASE =====
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

def build_task_keyboard(rows, user_data):
    # Builds a keyboard of task labels and saves the label→id mapping in user_data.
    buttons = []
    user_data["task_map"] = {}

    for r in rows:
        label = f"{r[1][:25]} — {format_time(r[2])}"
        buttons.append([label])
        user_data["task_map"][label] = r[0]

    buttons.append(["Back to menu"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ===== START COMMAND =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log.debug("START user=%s authorised=%s", user_id, user_id in ALLOWED_USERS)
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("This bot is private 💔")
        return

    await update.message.reply_text(
        "Hi! I'm your shared planner ❤️\n"
        "I'll help you not forget important things 🥰\n\n"
        "Let's plan something together ✨",
        reply_markup=main_keyboard
    )

# ===== FLOW HANDLERS =====
# Each function handles one step of a multi-step conversation.
# Contract: (text, user_data) -> (reply_text, keyboard_or_None)
# Return (None, None) to silently ignore the message and stay in the current step.
# user_data holds the state for the current flow (flow name, step name, and any collected values).

# --- Add flow ---
# Collects: task name → date → time → who → repeat schedule → saves to DB.

def handle_add_text(text, user_data):
    user_data["task_text"] = text
    user_data["step"] = "date"
    log.debug("ADD step=text -> date, task_text=%r", text)
    return "📅 Date (YYYY-MM-DD / today / tomorrow)", None

def handle_add_date(text, user_data):
    try:
        if text.lower() == "today":
            user_data["task_date"] = datetime.now(tz).date()
        elif text.lower() == "tomorrow":
            user_data["task_date"] = (datetime.now(tz) + timedelta(days=1)).date()
        else:
            user_data["task_date"] = datetime.strptime(text, "%Y-%m-%d").date()
        user_data["step"] = "time"
        log.debug("ADD step=date -> time, date=%s", user_data["task_date"])
        return "⏰ Time (HH:MM)", None
    except Exception:
        log.warning("ADD date parse error: %r", text)
        return "Wrong format 😢", None

def handle_add_time(text, user_data):
    try:
        t = datetime.strptime(text, "%H:%M").time()
        dt = tz.localize(datetime.combine(user_data["task_date"], t))
        user_data["task_time"] = dt
        user_data["step"] = "user"
        log.debug("ADD step=time -> user, time=%s", dt)
        return "👤 Who?", user_keyboard
    except Exception:
        log.warning("ADD time parse error: %r", text)
        return "Wrong time 😢", None

def handle_add_user(text, user_data):
    if text == MY_NAME:
        user_data["target_user"] = MY_ID
    elif text == PARTNER_NAME:
        user_data["target_user"] = PARTNER_ID
    else:
        log.debug("ADD user step: unrecognised name %r, ignoring", text)
        return None, None
    user_data["step"] = "repeat"
    log.debug("ADD step=user -> repeat, target_user=%s", user_data["target_user"])
    return "🔁 Repeat?", repeat_keyboard

def handle_add_repeat(text, user_data):
    repeat_map = {"One-time": "none", "Daily": "daily", "Weekly": "weekly"}
    if text not in repeat_map:
        log.debug("ADD repeat step: unrecognised value %r, ignoring", text)
        return None, None
    log.info("DB INSERT task text=%r time=%s repeat=%s",
             user_data["task_text"], user_data["task_time"].isoformat(), repeat_map[text])
    cursor.execute(
        "INSERT INTO tasks (user_id, text, time, repeat) VALUES (%s, %s, %s, %s)",
        (user_data["target_user"], user_data["task_text"],
         user_data["task_time"].isoformat(), repeat_map[text])
    )
    conn.commit()
    user_data.clear()
    return "Added ✨", main_keyboard

# --- Edit flow ---
# User picks a task from the list, then sends "new text | YYYY-MM-DD HH:MM".

def handle_edit_select(text, user_data):
    task_map = user_data.get("task_map", {})
    if text not in task_map:
        log.debug("EDIT SELECT: %r not in task_map, ignoring", text)
        return None, None
    user_data["edit_id"] = task_map[text]
    user_data["step"] = "confirm"
    log.debug("EDIT SELECT task_id=%s, waiting for edit input", task_map[text])
    return "Send: text | YYYY-MM-DD HH:MM", None

def handle_edit_confirm(text, user_data):
    try:
        new_text, new_time_str = text.split("|")
        new_time = tz.localize(datetime.strptime(new_time_str.strip(), "%Y-%m-%d %H:%M"))
        log.info("DB EDIT task_id=%s new_text=%r new_time=%s",
                 user_data["edit_id"], new_text.strip(), new_time.isoformat())
        cursor.execute(
            "UPDATE tasks SET text=%s, time=%s WHERE id=%s",
            (new_text.strip(), new_time.isoformat(), user_data["edit_id"])
        )
        conn.commit()
        user_data.clear()
        return "Updated ✏️", main_keyboard
    except Exception:
        log.warning("EDIT parse error: %r", text)
        return "Error 😢", None

# --- Delete flow ---
# User picks a task from the list; it is deleted immediately.

def handle_delete_select(text, user_data):
    task_map = user_data.get("task_map", {})
    if text not in task_map:
        return None, None
    log.info("DB DELETE task_id=%s", task_map[text])
    cursor.execute("DELETE FROM tasks WHERE id=%s", (task_map[text],))
    conn.commit()
    user_data.clear()
    return "Deleted ❌", main_keyboard

# --- Done flow ---
# User picks a task from the list; it is marked done. Multiple tasks can be marked in one session.

def handle_done_select(text, user_data):
    task_map = user_data.get("task_map", {})
    if text not in task_map:
        return None, None
    log.info("DB DONE task_id=%s", task_map[text])
    cursor.execute("UPDATE tasks SET done=1 WHERE id=%s", (task_map[text],))
    conn.commit()
    return random.choice(["Nice 💪", "Good 🔥"]), None

# ===== FLOW DISPATCH TABLE =====
# Maps flow name → step name → handler function.
# To add a new multi-step flow: add an entry here and write handler functions above.

FLOWS = {
    "add": {
        "text":    handle_add_text,
        "date":    handle_add_date,
        "time":    handle_add_time,
        "user":    handle_add_user,
        "repeat":  handle_add_repeat,
    },
    "edit": {
        "select":  handle_edit_select,
        "confirm": handle_edit_confirm,
    },
    "delete": {
        "select":  handle_delete_select,
    },
    "done": {
        "select":  handle_done_select,
    },
}

# ===== TOP-LEVEL COMMAND HANDLERS =====
# These handle single-message commands (main menu buttons and sub-menu buttons).
# Contract: (user_id, user_data) -> (reply_text, keyboard_or_None)
# Flow-starting commands set flow/step in user_data to begin a multi-step conversation.

def handle_cmd_add(user_id, user_data):
    log.debug("ADD starting")
    user_data["flow"] = "add"
    user_data["step"] = "text"
    return "📝 Task name?", None

def handle_cmd_tasks(user_id, user_data):
    log.debug("ROUTE -> Tasks menu")
    return "Choose:", tasks_keyboard

def handle_cmd_today(user_id, user_data):
    log.debug("ROUTE -> Today menu")
    return "Choose:", today_keyboard

def handle_cmd_edit(user_id, user_data):
    log.debug("ROUTE -> Edit mode")
    cursor.execute("SELECT id,text,time FROM tasks WHERE done=0")
    rows = cursor.fetchall()
    user_data["flow"] = "edit"
    user_data["step"] = "select"
    return "Choose task:", build_task_keyboard(rows, user_data)

def handle_cmd_delete(user_id, user_data):
    log.debug("ROUTE -> Delete mode")
    cursor.execute("SELECT id,text,time FROM tasks WHERE done=0")
    rows = cursor.fetchall()
    user_data["flow"] = "delete"
    user_data["step"] = "select"
    return "Choose:", build_task_keyboard(rows, user_data)

def handle_cmd_done(user_id, user_data):
    log.debug("ROUTE -> Done mode")
    cursor.execute("SELECT id,text,time FROM tasks WHERE done=0")
    rows = cursor.fetchall()
    user_data["flow"] = "done"
    user_data["step"] = "select"
    return "Mark done:", build_task_keyboard(rows, user_data)

def handle_cmd_all_tasks(user_id, user_data):
    cursor.execute("SELECT id,text,time FROM tasks")
    rows = cursor.fetchall()
    if not rows:
        return "No tasks", None
    msg = "📋 Tasks:\n\n" + "".join(f"{r[1]} — {format_time(r[2])}\n" for r in rows)
    return msg, None

def handle_cmd_my_tasks(user_id, user_data):
    cursor.execute("SELECT id,text,time FROM tasks WHERE user_id=%s", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        return "No tasks", None
    msg = "📋 Tasks:\n\n" + "".join(f"{r[1]} — {format_time(r[2])}\n" for r in rows)
    return msg, None

def handle_cmd_partner_tasks(user_id, user_data):
    cursor.execute("SELECT id,text,time FROM tasks WHERE user_id=%s", (get_partner_id(user_id),))
    rows = cursor.fetchall()
    if not rows:
        return "No tasks", None
    msg = "📋 Tasks:\n\n" + "".join(f"{r[1]} — {format_time(r[2])}\n" for r in rows)
    return msg, None

def handle_cmd_all_today(user_id, user_data):
    today = datetime.now(tz).date()
    cursor.execute("SELECT id,text,time,user_id FROM tasks WHERE done=0")
    rows = cursor.fetchall()
    tasks = [r for r in rows if datetime.fromisoformat(r[2]).date() == today]
    if not tasks:
        return "No tasks today ✨", None
    msg = "📅 Today:\n\n" + "".join(f"{r[1]} — {format_time(r[2])}\n" for r in tasks)
    return msg, None

def handle_cmd_my_today(user_id, user_data):
    today = datetime.now(tz).date()
    cursor.execute("SELECT id,text,time,user_id FROM tasks WHERE done=0")
    rows = cursor.fetchall()
    tasks = [r for r in rows if datetime.fromisoformat(r[2]).date() == today and r[3] == user_id]
    if not tasks:
        return "No tasks today ✨", None
    msg = "📅 Today:\n\n" + "".join(f"{r[1]} — {format_time(r[2])}\n" for r in tasks)
    return msg, None

def handle_cmd_partner_today(user_id, user_data):
    today = datetime.now(tz).date()
    cursor.execute("SELECT id,text,time,user_id FROM tasks WHERE done=0")
    rows = cursor.fetchall()
    tasks = [r for r in rows if datetime.fromisoformat(r[2]).date() == today and r[3] == get_partner_id(user_id)]
    if not tasks:
        return "No tasks today ✨", None
    msg = "📅 Today:\n\n" + "".join(f"{r[1]} — {format_time(r[2])}\n" for r in tasks)
    return msg, None

# ===== COMMAND DISPATCH TABLE =====
# Maps button text → handler function.
# To add a new command: add an entry here and write a handler function above.

COMMAND_HANDLERS = {
    "Add":           handle_cmd_add,
    "Tasks":         handle_cmd_tasks,
    "Today":         handle_cmd_today,
    "Edit":          handle_cmd_edit,
    "Delete":        handle_cmd_delete,
    "Done":          handle_cmd_done,
    "All tasks":     handle_cmd_all_tasks,
    "My tasks":      handle_cmd_my_tasks,
    "Partner tasks": handle_cmd_partner_tasks,
    "All today":     handle_cmd_all_today,
    "My today":      handle_cmd_my_today,
    "Partner today": handle_cmd_partner_today,
}

# ===== MESSAGE ROUTER =====
# Every incoming message passes through here. It checks in order:
# 1. Is the user allowed?
# 2. Are they going back to the main menu?
# 3. Are they mid-flow? Route to the current step's handler.
# 4. Is it a top-level command button? Route to the command handler.

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    log.debug("MSG user=%s text=%r flow=%s step=%s",
              user_id, text, context.user_data.get("flow"), context.user_data.get("step"))

    if user_id not in ALLOWED_USERS:
        log.warning("WHITELIST REJECT user=%s", user_id)
        await update.message.reply_text("This bot is private 💔")
        return

    if text == "Back to menu":
        context.user_data.clear()
        await update.message.reply_text("Back ✨", reply_markup=main_keyboard)
        return

    flow = context.user_data.get("flow")
    step = context.user_data.get("step")
    if flow and step:
        if flow in FLOWS and step in FLOWS[flow]:
            reply, keyboard = FLOWS[flow][step](text, context.user_data)
            if reply is not None:
                if keyboard is not None:
                    await update.message.reply_text(reply, reply_markup=keyboard)
                else:
                    await update.message.reply_text(reply)
        else:
            log.debug("FLOW=%s STEP=%s: no handler found, ignoring", flow, step)
        return

    if text in COMMAND_HANDLERS:
        reply, keyboard = COMMAND_HANDLERS[text](user_id, context.user_data)
        if reply is not None:
            if keyboard is not None:
                await update.message.reply_text(reply, reply_markup=keyboard)
            else:
                await update.message.reply_text(reply)
        return

    log.info("UNMATCHED text=%r user_data=%s", text, dict(context.user_data))

# ===== RUN =====

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
