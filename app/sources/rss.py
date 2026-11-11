"""Lecture des flux RSS."""
import asyncio
import hashlib
import logging
from dataclasses import dataclass

import aiohttp
import feedparser

logger = logging.getLogger(__name__)

SOURCES = [
    {"name": "Bourses (test)", "url": "https://news.google.com/rss/search?q=bourse+étudiants+Algérie&hl=fr&gl=DZ&ceid=DZ:fr"},
    {"name": "Stages (test)", "url": "https://news.google.com/rss/search?q=stage+offre+Algérie&hl=fr&gl=DZ&ceid=DZ:fr"},
    {"name": "Emploi (test)", "url": "https://news.google.com/rss/search?q=recrutement+emploi+Algérie&hl=fr&gl=DZ&ceid=DZ:fr"},
]


@dataclass(frozen=True)
class Item:
    item_id: str
    title: str
    url: str
    summary: str
    source: str


async def fetch_source(session: aiohttp.ClientSession, source: dict) -> list[Item]:
    """Télécharge et lit un flux. En cas d'erreur, retourne une liste vide (le bot continue)."""
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with session.get(source["url"], timeout=timeout) as resp:
            resp.raise_for_status()
            content = await resp.text()
    except Exception as exc:
        logger.warning("Source %s inaccessible : %s", source["name"], exc)
        return []

    feed = await asyncio.to_thread(feedparser.parse, content)
    items = []
    for entry in feed.entries:
        url = entry.get("link", "")
        title = entry.get("title", "").strip()
        if not url or not title:
            continue
        raw_id = entry.get("id") or url
        items.append(
            Item(
                item_id=hashlib.sha1(raw_id.encode("utf-8")).hexdigest(),
                title=title,
                url=url,
                summary=entry.get("summary", ""),
                source=source["name"],
            )
        )
    return items


async def fetch_all(sources: list[dict] = SOURCES) -> list[Item]:
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(fetch_source(session, s) for s in sources))
    return [item for sub in results for item in sub]