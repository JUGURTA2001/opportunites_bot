"""Envoi des alertes via Telegram (seul endroit du cycle d'alertes qui dépend d'aiogram)."""
import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.services.alerts import SendFn, UserBlocked


def make_sender(bot: Bot) -> SendFn:
    async def send(user_id: int, text: str) -> None:
        try:
            await bot.send_message(user_id, text)
        except TelegramForbiddenError as exc:  # bot bloqué ou conversation supprimée
            raise UserBlocked(str(exc)) from exc
        except TelegramRetryAfter as exc:  # trop d'envois : on attend puis on réessaie une fois
            await asyncio.sleep(exc.retry_after)
            await bot.send_message(user_id, text)

    return send
