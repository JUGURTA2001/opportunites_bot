"""Nettoyage des mots-clés et recherche dans le texte d'une offre (logique pure)."""
import re
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 40


def normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean_keyword(raw: str) -> tuple[str, str]:
    """Retourne (texte affiché, texte normalisé) ou lève ValueError avec un message lisible."""
    display = " ".join(raw.split()).lower()
    norm = normalize(raw)
    if len(norm) < MIN_LENGTH:
        raise ValueError(f"Mot-clé trop court ({MIN_LENGTH} caractères minimum).")
    if len(display) > MAX_LENGTH:
        raise ValueError(f"Mot-clé trop long ({MAX_LENGTH} caractères maximum).")
    return display, norm


def matches(text: str, keyword_norm: str) -> bool:
    """Vrai si TOUS les mots du mot-clé se retrouvent dans le texte.

    Un mot de 4 lettres ou plus peut aussi correspondre au début d'un mot du texte
    (« stage » trouve « stages »). Les mots courts doivent correspondre exactement.
    """
    words = keyword_norm.split()
    if not words:
        return False
    text_words = set(normalize(text).split())
    for word in words:
        if word in text_words:
            continue
        if len(word) >= 4 and any(t.startswith(word) for t in text_words):
            continue
        return False
    return True
