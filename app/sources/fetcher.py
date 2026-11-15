"""Téléchargement des sources avec aiohttp : délai, taille maximale, robots.txt."""
import asyncio
import time
from urllib.parse import urlsplit

import aiohttp

from app.sources.errors import FetchError
from app.sources.robots import robots_allows

USER_AGENT = "OpportunitesEtudiantsBot/1.0"
ROBOTS_TTL_SECONDS = 3600


class Fetcher:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        timeout: float = 15,
        max_bytes: int = 2_000_000,
    ):
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_bytes = max_bytes
        self._robots: dict[str, tuple[float, str]] = {}

    async def get(self, url: str) -> tuple[bytes, str | None]:
        """Retourne (contenu, encodage). Lève FetchError en cas de problème."""
        headers = {"User-Agent": USER_AGENT}
        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as resp:
                if resp.status != 200:
                    raise FetchError(f"HTTP {resp.status}", status=resp.status)
                body = bytearray()
                async for chunk in resp.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > self._max_bytes:
                        raise FetchError("réponse trop volumineuse")
                return bytes(body), resp.charset
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise FetchError(str(exc) or type(exc).__name__) from exc

    async def allowed(self, url: str) -> bool:
        """Vrai si robots.txt autorise la lecture de `url`.

        Pas de robots.txt (erreur 4xx) : autorisé. Erreur serveur ou réseau : on s'abstient
        pour cette fois (prudence), sans mémoriser le résultat.
        """
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > ROBOTS_TTL_SECONDS:
            try:
                body, charset = await self.get(origin + "/robots.txt")
                text = body.decode(charset or "utf-8", errors="replace")
            except FetchError as exc:
                if exc.status is not None and 400 <= exc.status < 500:
                    text = ""
                else:
                    return False
            cached = (time.monotonic(), text)
            self._robots[origin] = cached
        return robots_allows(cached[1], url, USER_AGENT)
