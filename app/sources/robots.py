"""Respect du fichier robots.txt (logique pure, testable sans réseau)."""
from urllib.robotparser import RobotFileParser


def robots_allows(robots_txt: str, url: str, agent: str) -> bool:
    """Vrai si `agent` a le droit de lire `url` d'après le contenu de robots.txt."""
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(agent, url)
