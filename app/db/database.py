"""Base de données SQLite (module `sqlite3` de la bibliothèque standard).

Les méthodes sont synchrones : les gestionnaires Telegram les appellent avec
`await asyncio.to_thread(...)` pour ne pas bloquer le bot.
"""
import sqlite3
import threading
from datetime import datetime, timezone

# Nombre maximum de mots-clés suivis par formule.
PLAN_LIMITS = {"free": 3, "premium": 20}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    plan       TEXT NOT NULL DEFAULT 'free',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    keyword      TEXT NOT NULL,
    keyword_norm TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    UNIQUE (user_id, keyword_norm)
);

-- Utilisée à l'étape 3 : offres déjà envoyées (anti-doublon).
CREATE TABLE IF NOT EXISTS seen_items (
    item_id    TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    first_seen TEXT NOT NULL
);
"""


def max_keywords(plan: str) -> int:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- Utilisateurs -------------------------------------------------------

    def upsert_user(
        self, user_id: int, username: str | None, first_name: str | None,
        reactivate: bool = False,
    ) -> None:
        """Crée l'utilisateur ou met à jour son nom. `reactivate` remet les alertes en marche."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    active     = CASE WHEN ? THEN 1 ELSE users.active END
                """,
                (user_id, username, first_name, _now(), int(reactivate)),
            )

    def get_user(self, user_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_active(self, user_id: int, active: bool) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE users SET active = ? WHERE user_id = ?", (int(active), user_id)
            )

    def set_plan(self, user_id: int, plan: str) -> bool:
        """Change la formule (free / premium). Retourne False si l'utilisateur n'existe pas."""
        if plan not in PLAN_LIMITS:
            raise ValueError(f"Formule inconnue : {plan}")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id)
            )
            return cur.rowcount > 0

    # --- Mots-clés ------------------------------------------------------------

    def add_keyword(self, user_id: int, keyword: str, keyword_norm: str) -> str:
        """Retourne « added », « exists » ou « limit » (limite de la formule atteinte)."""
        with self._lock, self._conn:
            user = self._conn.execute(
                "SELECT plan FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if user is None:
                raise KeyError(f"Utilisateur inconnu : {user_id}")
            exists = self._conn.execute(
                "SELECT 1 FROM subscriptions WHERE user_id = ? AND keyword_norm = ?",
                (user_id, keyword_norm),
            ).fetchone()
            if exists:
                return "exists"
            count = self._conn.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            if count >= max_keywords(user["plan"]):
                return "limit"
            self._conn.execute(
                "INSERT INTO subscriptions (user_id, keyword, keyword_norm, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, keyword, keyword_norm, _now()),
            )
            return "added"

    def list_keywords(self, user_id: int) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT keyword FROM subscriptions WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
        return [r["keyword"] for r in rows]

    def remove_keyword(self, user_id: int, keyword_norm: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM subscriptions WHERE user_id = ? AND keyword_norm = ?",
                (user_id, keyword_norm),
            )
            return cur.rowcount > 0

    # --- Statistiques ---------------------------------------------------------

    def stats(self) -> dict:
        with self._lock:
            users = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            active = self._conn.execute(
                "SELECT COUNT(*) FROM users WHERE active = 1"
            ).fetchone()[0]
            keywords = self._conn.execute(
                "SELECT COUNT(*) FROM subscriptions"
            ).fetchone()[0]
        return {"users": users, "active": active, "keywords": keywords}
