"""Objets partagés par toutes les sources."""
import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    """Adresse sans fragment (#...) ni paramètres de suivi (utm_...), pour repérer les doublons."""
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def is_http_url(url: str) -> bool:
    """Seuls http et https sont acceptés (pas de javascript:, file:, etc.)."""
    parts = urlsplit(url.strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


@dataclass(frozen=True)
class Source:
    name: str
    type: str  # "rss" ou "html"
    url: str
    link_pattern: str | None = None  # html : ne garder que les liens qui correspondent
    min_title_len: int = 25  # html : ignorer les liens au texte trop court
    enabled: bool = True


@dataclass(frozen=True)
class Item:
    source: str
    title: str
    url: str
    summary: str = ""

    @property
    def item_id(self) -> str:
        return hashlib.sha1(canonical_url(self.url).encode("utf-8")).hexdigest()[:20]
