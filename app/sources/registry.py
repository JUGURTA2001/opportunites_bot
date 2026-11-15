"""Chargement de la liste des sources depuis le fichier sources.json."""
import json
import re

from app.sources.models import Source, is_http_url


class SourceConfigError(ValueError):
    """Le fichier sources.json contient une erreur (message lisible)."""


def load_sources(path: str) -> list[Source]:
    """Retourne les sources actives. Lève FileNotFoundError ou SourceConfigError."""
    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise SourceConfigError(f"{path} : JSON invalide ({exc})") from exc
    if not isinstance(data, list):
        raise SourceConfigError(f"{path} : le fichier doit contenir une liste de sources")

    sources: list[Source] = []
    names: set[str] = set()
    for index, entry in enumerate(data, start=1):
        label = f"source n°{index}"
        if not isinstance(entry, dict):
            raise SourceConfigError(f"{label} : objet attendu")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SourceConfigError(f"{label} : « name » manquant")
        label = f"source « {name} »"
        if name in names:
            raise SourceConfigError(f"{label} : nom déjà utilisé")
        names.add(name)
        if entry.get("type") not in ("rss", "html"):
            raise SourceConfigError(f"{label} : « type » doit être « rss » ou « html »")
        url = entry.get("url")
        if not isinstance(url, str) or not is_http_url(url):
            raise SourceConfigError(f"{label} : « url » doit commencer par http:// ou https://")
        pattern = entry.get("link_pattern")
        if pattern is not None:
            try:
                re.compile(pattern)
            except (re.error, TypeError) as exc:
                raise SourceConfigError(f"{label} : « link_pattern » invalide ({exc})") from exc
        min_len = entry.get("min_title_len", 25)
        if not isinstance(min_len, int) or isinstance(min_len, bool) or min_len < 1:
            raise SourceConfigError(f"{label} : « min_title_len » doit être un entier positif")
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise SourceConfigError(f"{label} : « enabled » doit être true ou false")
        if enabled:
            sources.append(Source(name, entry["type"], url, pattern, min_len, True))
    return sources
