import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot

from agent import agent

load_dotenv()

DEMANDE = (
    "C'est dimanche soir. Fais-moi le bilan de la semaine qui se termine "
    "et le plan de la semaine prochaine."
)


async def envoyer(texte: str):
    bot = Bot(os.environ["TELEGRAM_TOKEN"])
    async with bot:
        await bot.send_message(chat_id=int(os.environ["TELEGRAM_CHAT_ID"]), text=texte)


if __name__ == "__main__":
    bilan = agent([{"role": "user", "content": DEMANDE}])
    asyncio.run(envoyer(bilan))
    print("Bilan envoyé !")