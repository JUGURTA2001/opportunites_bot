"""Tests des offres, des envois et de la migration. Lancer : python -m unittest -v"""
import os
import sqlite3
import tempfile
import unittest

from app.db.database import Database

OLD_SCHEMA_ETAPE_2 = """
CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
    plan TEXT NOT NULL DEFAULT 'free', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE seen_items (item_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
    first_seen TEXT NOT NULL);
INSERT INTO seen_items VALUES ('vieux', 'Ancienne offre', 'https://a.dz/1', '2026-01-01T00:00:00+00:00');
"""


def row(n, source="S"):
    return (f"id{n}", source, f"Titre {n}", f"https://a.dz/{n}", f"Résumé {n}")


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.init_schema()
        self.addCleanup(self.db.close)


class TestItems(DatabaseTestCase):
    def test_ajout_sans_doublon(self):
        self.assertEqual(self.db.add_items([row(1), row(2)], pending=True), ["id1", "id2"])
        self.assertEqual(self.db.add_items([row(2), row(3)], pending=True), ["id3"])

    def test_en_attente_ou_memorise(self):
        self.db.add_items([row(1)], pending=False)
        self.db.add_items([row(2), row(3)], pending=True)
        self.assertEqual([i["item_id"] for i in self.db.pending_items()], ["id2", "id3"])

    def test_une_offre_deja_memorisee_ne_devient_pas_en_attente(self):
        self.db.add_items([row(1)], pending=False)
        self.assertEqual(self.db.add_items([row(1)], pending=True), [])
        self.assertEqual(self.db.pending_items(), [])

    def test_clear_pending(self):
        self.db.add_items([row(1), row(2)], pending=True)
        self.db.clear_pending(["id1"])
        self.assertEqual([i["item_id"] for i in self.db.pending_items()], ["id2"])

    def test_expiration(self):
        self.db.add_items([row(1), row(2)], pending=True)
        self.db._conn.execute(
            "UPDATE seen_items SET first_seen = '2000-01-01T00:00:00+00:00' WHERE item_id = 'id1'"
        )
        self.assertEqual(self.db.expire_pending(24), 1)
        self.assertEqual([i["item_id"] for i in self.db.pending_items()], ["id2"])

    def test_sources_connues(self):
        self.assertFalse(self.db.is_source_known("S"))
        self.db.mark_source_known("S")
        self.db.mark_source_known("S")  # sans effet
        self.assertTrue(self.db.is_source_known("S"))


class TestSentAlerts(DatabaseTestCase):
    def test_envoi_enregistre_une_seule_fois(self):
        self.db.upsert_user(1, "a", "A")
        self.assertFalse(self.db.was_sent(1, "id1"))
        self.db.record_sent(1, "id1")
        self.db.record_sent(1, "id1")
        self.assertTrue(self.db.was_sent(1, "id1"))
        self.assertFalse(self.db.was_sent(2, "id1"))


class TestActiveSubscribers(DatabaseTestCase):
    def test_filtre(self):
        for uid in (1, 2, 3):
            self.db.upsert_user(uid, f"u{uid}", f"U{uid}")
        self.db.add_keyword(1, "Bourse", "bourse")
        self.db.add_keyword(1, "stage informatique", "stage informatique")
        self.db.add_keyword(2, "emploi", "emploi")
        self.db.set_active(2, False)  # en pause ; l'utilisateur 3 n'a aucun mot-clé
        self.assertEqual(
            self.db.active_subscribers(),
            {1: [("Bourse", "bourse"), ("stage informatique", "stage informatique")]},
        )


class TestMigration(unittest.TestCase):
    def test_base_de_l_etape_2_mise_a_jour(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ancienne.db")
            old = sqlite3.connect(path)
            old.executescript(OLD_SCHEMA_ETAPE_2)
            old.commit()
            old.close()

            db = Database(path)
            try:
                db.init_schema()
                db.init_schema()  # peut être relancée sans erreur
                self.assertEqual(db.pending_items(), [])  # l'ancienne offre n'est pas « en attente »
                self.assertEqual(db.add_items([row(1)], pending=True), ["id1"])
                self.assertEqual(db.pending_items()[0]["source"], "S")
                old_row = db._conn.execute(
                    "SELECT source, pending FROM seen_items WHERE item_id='vieux'"
                ).fetchone()
                self.assertEqual(tuple(old_row), ("", 0))
            finally:
                # Windows : le fichier doit être fermé AVANT la suppression du dossier temporaire.
                db.close()


if __name__ == "__main__":
    unittest.main()