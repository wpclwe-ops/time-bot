from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, time
import os
import pytz
import random

TOKEN = os.getenv("TOKEN")

tz = pytz.timezone("Europe/Warsaw")

tasks = {}

keyboard = ReplyKeyboardMarkup(
    [
        ["Add task", "Show tasks"],
        ["Delete task", "Done"]
    ],
    resize_keyboard=True
)

motivation = [
    "Nice job 💪",
    "You’re doing great 🔥",
    "Keep going 🚀",
    "Proud of you ❤️"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in tasks:
        tasks[user_id] = []

    # утренний план (каждый день в 08:00)
    context.job_queue.run_daily(
        send_daily_plan,
        time=time(hour=8, minute=0, tzinfo=tz),
        data={"chat_id": update.effective_chat.id, "user_id": user_id}
    )

    await update.message.reply_text(
        "Hi! I'm your task diary bot 📓\n"
        "Add tasks, track them and stay productive 💫",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in tasks:
        tasks[user_id] = []

    # ➕ ADD TASK
    if text == "Add task":
        await update.message.reply_text(
            "Send task like:\nTask | YYYY-MM-DD HH:MM"
        )
        return

    # 📋 SHOW TASKS
    if text == "Show tasks":
        user_tasks = tasks[user_id]

        if not user_tasks:
            await update.message.reply_text("No tasks yet")
            return

        msg = ""
        for i, t in enumerate(user_tasks):
            msg += f"{i+1}. {t['text']} — {t['time']}\n"

        await update.message.reply_text(msg)
        return

    # ❌ DELETE
    if text == "Delete task":
        await update.message.reply_text("Send task number to delete")
        context.user_data["mode"] = "delete"
        return

    # ✅ DONE
    if text == "Done":
        await update.message.reply_text("Send task number completed")
        context.user_data["mode"] = "done"
        return

    # 🔢 ОБРАБОТКА НОМЕРОВ
    if context.user_data.get("mode") in ["delete", "done"]:
        try:
            index = int(text) - 1
            task = tasks[user_id][index]

            if context.user_data["mode"] == "delete":
                tasks[user_id].pop(index)
                await update.message.reply_text("Deleted ❌")

            else:
                tasks[user_id].pop(index)
                await update.message.reply_text(random.choice(motivation))

            context.user_data["mode"] = None
        except:
            await update.message.reply_text("Invalid number")
        return

    # 🧠 ДОБАВЛЕНИЕ ЗАДАЧИ
    if "|" in text:
        try:
            task_text, task_time = text.split("|")
            task_time = tz.localize(datetime.strptime(task_time.strip(), "%Y-%m-%d %H:%M"))

            tasks[user_id].append({
                "text": task_text.strip(),
                "time": task_time
            })

            # 🔔 НАПОМИНАНИЕ
            delay = (task_time - datetime.now(tz)).total_seconds()

            if delay > 0:
                context.job_queue.run_once(
                    send_reminder,
                    when=delay,
                    data={
                        "chat_id": update.effective_chat.id,
                        "text": task_text
                    }
                )

            await update.message.reply_text("Task added ✅")

        except:
            await update.message.reply_text("Wrong format 😢")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        job.data["chat_id"],
        f"⏰ Reminder: {job.data['text']}"
    )

async def send_daily_plan(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    chat_id = context.job.data["chat_id"]

    user_tasks = tasks.get(user_id, [])

    if not user_tasks:
        await context.bot.send_message(chat_id, "No tasks for today ✨")
        return

    msg = "🌅 Your plan for today:\n\n"

    for t in user_tasks:
        msg += f"- {t['text']} ({t['time'].strftime('%H:%M')})\n"

    await context.bot.send_message(chat_id, msg)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
