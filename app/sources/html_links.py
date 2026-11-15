"""Extraction des liens d'une page web d'annonces (bibliothèque standard, sans dépendance).

Principe : on garde les liens dont le texte est assez long pour être un titre d'annonce,
et (en option) dont l'adresse correspond à un motif. Pour chaque site, ajustez
`link_pattern` et `min_title_len` dans sources.json.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.sources.models import Item, canonical_url, is_http_url

MAX_TITLE = 300
MAX_ITEMS = 100


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._skip = 0  # profondeur dans <script> / <style>

    def _finish(self):
        if self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "a":
            self._finish()
            self._href = dict(attrs).get("href") or ""

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a":
            self._finish()

    def handle_data(self, data):
        if self._href is not None and not self._skip:
            self._text.append(data)

    def close(self):
        super().close()
        self._finish()


def decode_body(body: bytes, charset: str | None) -> str:
    """Décode une page en tolérant les erreurs (jamais d'exception)."""
    for encoding in (charset, "utf-8"):
        if not encoding:
            continue
        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def extract_links(
    page: str,
    base_url: str,
    source_name: str,
    link_pattern: str | None = None,
    min_title_len: int = 25,
) -> list[Item]:
    parser = _LinkParser()
    parser.feed(page)
    parser.close()
    pattern = re.compile(link_pattern) if link_pattern else None
    base = canonical_url(base_url)

    items: list[Item] = []
    seen: set[str] = set()
    for href, text in parser.links:
        href = href.strip()
        if not href or href.startswith("#"):
            continue
        url = urljoin(base_url, href)
        if not is_http_url(url) or len(text) < min_title_len:
            continue
        if pattern and not pattern.search(url):
            continue
        key = canonical_url(url)
        if key == base or key in seen:
            continue
        seen.add(key)
        items.append(Item(source=source_name, title=text[:MAX_TITLE], url=url))
        if len(items) >= MAX_ITEMS:
            break
    return items
