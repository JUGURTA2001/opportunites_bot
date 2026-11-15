"""Planification : lance un cycle d'alertes à intervalle régulier."""
import asyncio
import logging

log = logging.getLogger(__name__)


async def run_forever(runner, interval_seconds: float) -> None:
    """Boucle infinie ; une erreur dans un cycle est journalisée et n'arrête pas le bot."""
    while True:
        try:
            await runner.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Erreur pendant la vérification des sources")
        await asyncio.sleep(interval_seconds)
