import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app import config
from app.bot.handlers import router
from app.db.database import Database
from app.services.scheduler import run_scheduler

COMMANDS = [
    BotCommand(command="abonner", description="Suivre un mot-clé"),
    BotCommand(command="mes_alertes", description="Voir mes alertes"),
    BotCommand(command="retirer", description="Supprimer une alerte"),
    BotCommand(command="stop", description="Mettre les alertes en pause"),
    BotCommand(command="help", description="Aide"),
]


async def main():
    logging.basicConfig(level=logging.INFO)
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN introuvable : vérifiez votre fichier .env")

    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    db = Database(config.DB_PATH)
    db.init_schema()

    dp = Dispatcher(db=db)
    dp.include_router(router)

    bot = Bot(token=config.BOT_TOKEN)
    try:
        await bot.set_my_commands(COMMANDS)
    except Exception as exc:
        logging.warning("Impossible de définir les commandes : %s", exc)

    scheduler_task = asyncio.create_task(run_scheduler(bot, db))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())