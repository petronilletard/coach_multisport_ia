import asyncio
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import agent

load_dotenv()
MON_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
messages = []  # la conversation en cours


async def repondre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sécurité : le coach ne répond qu'à moi
    if update.effective_chat.id != MON_CHAT_ID:
        return

    messages.append({"role": "user", "content": update.message.text})
    await update.message.chat.send_action("typing")  # "Coach IA est en train d'écrire..."

    reponse = await asyncio.to_thread(agent, messages)
    await update.message.reply_text(reponse)


async def nouveau(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /nouveau : repartir d'une conversation vide."""
    if update.effective_chat.id != MON_CHAT_ID:
        return
    messages.clear()
    await update.message.reply_text("Nouvelle conversation ! 🏊‍♀️🏃‍♀️🚴‍♀️")


app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(CommandHandler("nouveau", nouveau))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, repondre))
print("Coach démarré sur Telegram !")
app.run_polling()