import asyncio
import contextlib
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app import config
from app.bot.handlers import router
from app.bot.notifier import make_sender
from app.db.database import Database
from app.services.alerts import CycleRunner
from app.services.scheduler import run_forever
from app.sources.fetcher import Fetcher
from app.sources.registry import SourceConfigError, load_sources

COMMANDS = [
    BotCommand(command="abonner", description="Suivre un mot-clé"),
    BotCommand(command="mes_alertes", description="Voir mes alertes"),
    BotCommand(command="retirer", description="Supprimer une alerte"),
    BotCommand(command="stop", description="Mettre les alertes en pause"),
    BotCommand(command="help", description="Aide"),
]


def read_sources():
    try:
        sources = load_sources(config.SOURCES_PATH)
    except FileNotFoundError:
        logging.warning("%s introuvable : aucune source à surveiller.", config.SOURCES_PATH)
        return []
    except SourceConfigError as exc:
        raise SystemExit(f"Erreur dans {config.SOURCES_PATH} : {exc}") from exc
    logging.info("%d source(s) active(s).", len(sources))
    return sources


async def main():
    logging.basicConfig(level=logging.INFO)
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN introuvable : vérifiez votre fichier .env")

    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    db = Database(config.DB_PATH)
    db.init_schema()
    sources = read_sources()

    bot = Bot(token=config.BOT_TOKEN)
    try:
        await bot.set_my_commands(COMMANDS)
    except Exception as exc:  # le bot reste utilisable sans le menu de commandes
        logging.warning("Impossible de définir les commandes : %s", exc)

    async with aiohttp.ClientSession() as session:
        runner = CycleRunner(db, sources, Fetcher(session), make_sender(bot))
        # `db` et `runner` sont injectés par nom dans les gestionnaires qui les demandent.
        dp = Dispatcher(db=db, runner=runner)
        dp.include_router(router)

        checker = asyncio.create_task(run_forever(runner, config.CHECK_INTERVAL_MINUTES * 60))
        try:
            await dp.start_polling(bot)
        finally:
            checker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await checker
            db.close()


if __name__ == "__main__":
    asyncio.run(main())
