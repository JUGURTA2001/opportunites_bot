"""Lit une source (RSS ou page web) et retourne ses offres."""
from app.sources.errors import SourceError
from app.sources.html_links import decode_body, extract_links
from app.sources.models import Item, Source
from app.sources.rss import parse_feed


async def load_items(source: Source, fetcher) -> list[Item]:
    """`fetcher` doit offrir `await get(url) -> (bytes, charset)` et `await allowed(url) -> bool`."""
    if source.type == "html" and not await fetcher.allowed(source.url):
        raise SourceError("lecture interdite par le fichier robots.txt du site")
    body, charset = await fetcher.get(source.url)
    if source.type == "rss":
        return parse_feed(body, source.name)
    page = decode_body(body, charset)
    return extract_links(page, source.url, source.name, source.link_pattern, source.min_title_len)
