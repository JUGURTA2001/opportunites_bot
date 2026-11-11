"""Vérification planifiée : lecture des sources, anti-doublon, envoi des alertes."""
import asyncio
import html
import logging
from collections import defaultdict

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app import config
from app.db.database import Database
from app.services.matching import matches
from app.sources.rss import fetch_all

logger = logging.getLogger(__name__)


async def check_sources(bot: Bot, db: Database) -> None:
    # Premier lancement : on mémorise les offres existantes sans rien envoyer,
    # pour ne pas inonder les utilisateurs avec d'anciennes offres.
    first_run = await asyncio.to_thread(db.count_seen) == 0

    items = await fetch_all()
    subscriptions = await asyncio.to_thread(db.active_subscriptions)
    logger.info("%d offres lues, %d abonnements actifs", len(items), len(subscriptions))

    sent = 0
    for item in items:
        is_new = await asyncio.to_thread(db.mark_seen, item.item_id, item.title, item.url)
        if not is_new or first_run:
            continue

        text = f"{item.title} {item.summary}"
        keywords_by_user = defaultdict(list)
        for user_id, display, norm in subscriptions:
            if matches(text, norm):
                keywords_by_user[user_id].append(display)

        for user_id, keywords in keywords_by_user.items():
            message = (
                f"🔔 <b>{html.escape(item.title)}</b>\n"
                f"Source : {html.escape(item.source)}\n"
                f"Mots-clés : {html.escape(', '.join(keywords))}\n"
                f"{html.escape(item.url)}"
            )
            if await send_alert(bot, db, user_id, message):
                sent += 1
            await asyncio.sleep(0.05)  # limite Telegram : ~30 messages/seconde

    logger.info("Vérification terminée : %d alertes envoyées", sent)


async def send_alert(bot: Bot, db: Database, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
        return True
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        return await send_alert(bot, db, user_id, text)
    except TelegramForbiddenError:
        # L'utilisateur a bloqué le bot : on met ses alertes en pause.
        await asyncio.to_thread(db.set_active, user_id, False)
        return False
    except Exception as exc:
        logger.warning("Envoi impossible à %s : %s", user_id, exc)
        return False


async def run_scheduler(bot: Bot, db: Database) -> None:
    """Boucle infinie : une vérification toutes les CHECK_INTERVAL_MINUTES minutes."""
    while True:
        try:
            await check_sources(bot, db)
        except Exception:
            logger.exception("Erreur pendant la vérification")
        await asyncio.sleep(config.CHECK_INTERVAL_MINUTES * 60)