"""Base de données SQLite (module `sqlite3` de la bibliothèque standard).

Les méthodes sont synchrones : les gestionnaires Telegram les appellent avec
`await asyncio.to_thread(...)` pour ne pas bloquer le bot.
"""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

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

-- Offres déjà rencontrées. `pending = 1` : à envoyer aux abonnés concernés.
CREATE TABLE IF NOT EXISTS seen_items (
    item_id    TEXT PRIMARY KEY,
    source     TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    summary    TEXT NOT NULL DEFAULT '',
    pending    INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL
);

-- Sources déjà lues au moins une fois (le premier passage ne déclenche aucune alerte).
CREATE TABLE IF NOT EXISTS known_sources (
    name      TEXT PRIMARY KEY,
    first_run TEXT NOT NULL
);

-- Évite d'envoyer deux fois la même offre au même utilisateur.
CREATE TABLE IF NOT EXISTS sent_alerts (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (user_id, item_id)
);
"""

# Colonnes ajoutées à `seen_items` à l'étape 3 (pour les bases créées à l'étape 2).
_SEEN_ITEMS_COLUMNS = (
    ("source", "TEXT NOT NULL DEFAULT ''"),
    ("summary", "TEXT NOT NULL DEFAULT ''"),
    ("pending", "INTEGER NOT NULL DEFAULT 0"),
)


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
        """Crée les tables et met à jour une base de l'étape précédente."""
        with self._lock:
            self._conn.executescript(SCHEMA)
            existing = {r["name"] for r in self._conn.execute("PRAGMA table_info(seen_items)")}
            for name, ddl in _SEEN_ITEMS_COLUMNS:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE seen_items ADD COLUMN {name} {ddl}")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_items_pending ON seen_items(pending)"
            )
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

    def active_subscribers(self) -> dict[int, list[tuple[str, str]]]:
        """Utilisateurs actifs ayant au moins un mot-clé : {id: [(affiché, normalisé), ...]}."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT s.user_id, s.keyword, s.keyword_norm
                FROM subscriptions s JOIN users u ON u.user_id = s.user_id
                WHERE u.active = 1
                ORDER BY s.user_id, s.id
                """
            ).fetchall()
        result: dict[int, list[tuple[str, str]]] = {}
        for r in rows:
            result.setdefault(r["user_id"], []).append((r["keyword"], r["keyword_norm"]))
        return result

    # --- Sources et offres ------------------------------------------------------

    def is_source_known(self, name: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM known_sources WHERE name = ?", (name,)
            ).fetchone()
        return row is not None

    def mark_source_known(self, name: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO known_sources (name, first_run) VALUES (?, ?)",
                (name, _now()),
            )

    def add_items(
        self, rows: list[tuple[str, str, str, str, str]], pending: bool
    ) -> list[str]:
        """Enregistre les offres (item_id, source, title, url, summary) encore inconnues.

        Retourne les identifiants réellement ajoutés (les doublons sont ignorés).
        """
        added: list[str] = []
        with self._lock, self._conn:
            for item_id, source, title, url, summary in rows:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO seen_items "
                    "(item_id, source, title, url, summary, pending, first_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item_id, source, title, url, summary, int(pending), _now()),
                )
                if cur.rowcount:
                    added.append(item_id)
        return added

    def pending_items(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM seen_items WHERE pending = 1 ORDER BY rowid"
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_pending(self, item_ids: list[str]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE seen_items SET pending = 0 WHERE item_id = ?",
                [(i,) for i in item_ids],
            )

    def expire_pending(self, max_age_hours: float) -> int:
        """Abandonne les offres en attente depuis trop longtemps (envoi impossible)."""
        limit = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat(
            timespec="seconds"
        )
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE seen_items SET pending = 0 WHERE pending = 1 AND first_seen < ?",
                (limit,),
            )
            return cur.rowcount

    def was_sent(self, user_id: int, item_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM sent_alerts WHERE user_id = ? AND item_id = ?",
                (user_id, item_id),
            ).fetchone()
        return row is not None

    def record_sent(self, user_id: int, item_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO sent_alerts (user_id, item_id, sent_at) VALUES (?, ?, ?)",
                (user_id, item_id, _now()),
            )

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
