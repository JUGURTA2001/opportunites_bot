"""Lecture des flux RSS 2.0 et Atom avec la bibliothèque standard (aucune installation)."""
import html
import re
import xml.etree.ElementTree as ET

from app.sources.errors import FeedError
from app.sources.models import Item, is_http_url

_TAGS = re.compile(r"<[^>]+>")
MAX_TITLE = 300
MAX_SUMMARY = 500


def clean_text(raw: str | None, limit: int) -> str:
    """Retire les balises HTML, décode les entités (&amp;...) et raccourcit."""
    text = html.unescape(_TAGS.sub(" ", raw or ""))
    return " ".join(text.split())[:limit]


def _local(tag: str) -> str:
    """Nom de balise sans espace de noms : '{http://www.w3.org/2005/Atom}entry' -> 'entry'."""
    return tag.rsplit("}", 1)[-1]


def _pick_link(children: list[ET.Element], guid: str) -> str:
    candidates = []
    for child in children:
        if _local(child.tag) != "link":
            continue
        href = (child.get("href") or "").strip()
        text = (child.text or "").strip()
        rel = child.get("rel", "alternate")
        value = href or text
        if value and rel in ("alternate", ""):
            candidates.append(value)
    if not candidates and guid:
        candidates.append(guid)
    for value in candidates:
        if is_http_url(value):
            return value.strip()
    return ""


def parse_feed(content: bytes | str, source_name: str) -> list[Item]:
    """Transforme un flux RSS/Atom en liste d'offres. Lève FeedError si le contenu est invalide."""
    # Les déclarations d'entités (<!ENTITY>) servent aux attaques par expansion : on refuse.
    needle = b"<!entity" if isinstance(content, bytes) else "<!entity"
    if needle in content.lower():
        raise FeedError("flux refusé : déclarations d'entités non autorisées")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FeedError(f"flux illisible : {exc}") from exc
    if _local(root.tag) not in ("rss", "feed", "RDF"):
        raise FeedError("ce n'est pas un flux RSS ou Atom")

    items: list[Item] = []
    seen: set[str] = set()
    for element in root.iter():
        if not isinstance(element.tag, str) or _local(element.tag) not in ("item", "entry"):
            continue
        children = list(element)
        fields: dict[str, str] = {}
        for child in children:
            name = _local(child.tag)
            if name in ("title", "summary", "description", "content", "guid", "id"):
                fields.setdefault(name, "".join(child.itertext()))
        title = clean_text(fields.get("title"), MAX_TITLE)
        url = _pick_link(children, (fields.get("guid") or fields.get("id") or "").strip())
        if not title or not url:
            continue
        summary = clean_text(
            fields.get("summary") or fields.get("description") or fields.get("content"),
            MAX_SUMMARY,
        )
        item = Item(source=source_name, title=title, url=url, summary=summary)
        if item.item_id not in seen:
            seen.add(item.item_id)
            items.append(item)
    return items
