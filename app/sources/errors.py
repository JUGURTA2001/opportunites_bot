"""Erreurs liées aux sources (messages lisibles, affichés par /verifier)."""


class SourceError(Exception):
    """Une source n'a pas pu être lue."""


class FetchError(SourceError):
    """Échec de téléchargement (réseau, délai dépassé, code HTTP, taille)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class FeedError(SourceError):
    """Le contenu reçu n'est pas un flux RSS ou Atom valide."""
