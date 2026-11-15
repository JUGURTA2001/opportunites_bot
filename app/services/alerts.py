"""Cycle d'alertes : lire les sources, repérer les nouvelles offres, prévenir les abonnés.

Ce module ne dépend ni de Telegram ni du réseau : le téléchargement (`fetcher`) et l'envoi
(`send`) sont fournis de l'extérieur, ce qui permet de tout tester sans connexion.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.db.database import Database
from app.services.matching import matches
from app.sources.loader import load_items
from app.sources.models import Source

log = logging.getLogger(__name__)

# Plus d'offres nouvelles d'un coup pour une seule source = changement de structure probable.
MAX_NEW_PER_SOURCE = 30
MAX_ALERTS_PER_USER_PER_CYCLE = 10
PENDING_MAX_AGE_HOURS = 24
SEND_DELAY_SECONDS = 0.05  # reste sous les limites d'envoi de Telegram

SendFn = Callable[[int, str], Awaitable[None]]


class UserBlocked(Exception):
    """L'utilisateur a bloqué le bot ou supprimé la conversation."""


@dataclass
class CycleReport:
    sources_ok: int = 0
    sources_failed: int = 0
    baselined: int = 0  # offres mémorisées au premier passage, sans alerte
    new_items: int = 0
    alerts_sent: int = 0
    errors: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines = [
            "✅ Vérification terminée",
            f"Sources lues : {self.sources_ok} (échecs : {self.sources_failed})",
            f"Nouvelles offres : {self.new_items}"
            + (f" (+{self.baselined} mémorisées au premier passage)" if self.baselined else ""),
            f"Alertes envoyées : {self.alerts_sent}",
        ]
        if self.errors:
            lines.append("")
            lines.append("⚠️ Problèmes :")
            lines += [f"• {e}" for e in self.errors[:5]]
            if len(self.errors) > 5:
                lines.append(f"• … et {len(self.errors) - 5} autres")
        return "\n".join(lines)


def format_alert(item: dict, keywords: list[str]) -> str:
    title = item["title"][:300]
    return (
        f"🔔 {title}\n{item['url']}\n\n"
        f"Mot-clé : {', '.join(keywords)} · Source : {item['source']}"
    )


async def collect(db: Database, sources: list[Source], fetcher, report: CycleReport) -> None:
    """Lit chaque source et enregistre les offres nouvelles."""
    for source in sources:
        try:
            items = await load_items(source, fetcher)
        except Exception as exc:  # une source en panne ne doit pas arrêter les autres
            report.sources_failed += 1
            report.errors.append(f"{source.name} : {exc}")
            log.warning("Source %s en échec : %s", source.name, exc)
            continue
        report.sources_ok += 1
        rows = [(i.item_id, i.source, i.title, i.url, i.summary) for i in items]

        if not await asyncio.to_thread(db.is_source_known, source.name):
            # Premier passage : on mémorise l'existant sans prévenir personne.
            if rows:
                added = await asyncio.to_thread(db.add_items, rows, False)
                report.baselined += len(added)
                await asyncio.to_thread(db.mark_source_known, source.name)
            continue

        new_ids = await asyncio.to_thread(db.add_items, rows, True)
        if len(new_ids) > MAX_NEW_PER_SOURCE:
            await asyncio.to_thread(db.clear_pending, new_ids)
            report.errors.append(
                f"{source.name} : {len(new_ids)} offres nouvelles d'un coup, ignorées "
                "(changement de structure du site ?)"
            )
            continue
        report.new_items += len(new_ids)


async def dispatch(db: Database, send: SendFn, report: CycleReport) -> None:
    """Envoie chaque offre en attente aux abonnés dont un mot-clé correspond."""
    await asyncio.to_thread(db.expire_pending, PENDING_MAX_AGE_HOURS)
    items = await asyncio.to_thread(db.pending_items)
    if not items:
        return
    subscribers = await asyncio.to_thread(db.active_subscribers)
    sent_count: dict[int, int] = {}
    overflow: dict[int, int] = {}
    blocked: set[int] = set()

    for item in items:
        text = f"{item['title']} {item['summary']}"
        retry_later = False
        for user_id, keywords in subscribers.items():
            if user_id in blocked:
                continue
            found = [shown for shown, norm in keywords if matches(text, norm)]
            if not found:
                continue
            if await asyncio.to_thread(db.was_sent, user_id, item["item_id"]):
                continue
            if sent_count.get(user_id, 0) >= MAX_ALERTS_PER_USER_PER_CYCLE:
                overflow[user_id] = overflow.get(user_id, 0) + 1
                continue
            try:
                await send(user_id, format_alert(item, found))
            except UserBlocked:
                blocked.add(user_id)
                await asyncio.to_thread(db.set_active, user_id, False)
                continue
            except Exception:
                log.exception("Envoi impossible à %s", user_id)
                retry_later = True  # l'offre reste en attente : nouvel essai au prochain cycle
                continue
            await asyncio.to_thread(db.record_sent, user_id, item["item_id"])
            sent_count[user_id] = sent_count.get(user_id, 0) + 1
            report.alerts_sent += 1
            await asyncio.sleep(SEND_DELAY_SECONDS)
        if not retry_later:
            await asyncio.to_thread(db.clear_pending, [item["item_id"]])

    for user_id, extra in overflow.items():
        try:
            await send(
                user_id,
                f"ℹ️ {extra} autres offres correspondent à vos alertes. "
                "Précisez vos mots-clés (/retirer, /abonner) pour en recevoir moins.",
            )
        except Exception:
            log.exception("Message de synthèse impossible pour %s", user_id)


class CycleRunner:
    """Exécute un cycle complet ; deux cycles ne se chevauchent jamais."""

    def __init__(self, db: Database, sources: list[Source], fetcher, send: SendFn):
        self._db = db
        self._sources = sources
        self._fetcher = fetcher
        self._send = send
        self._lock = asyncio.Lock()

    async def run(self) -> CycleReport | None:
        """Retourne le rapport, ou None si un cycle est déjà en cours."""
        if self._lock.locked():
            return None
        async with self._lock:
            report = CycleReport()
            await collect(self._db, self._sources, self._fetcher, report)
            await dispatch(self._db, self._send, report)
            log.info(
                "Cycle : %d source(s) lue(s), %d échec(s), %d nouvelle(s) offre(s), %d alerte(s)",
                report.sources_ok, report.sources_failed, report.new_items, report.alerts_sent,
            )
            return report
