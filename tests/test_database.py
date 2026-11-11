"""Tests de la base de données. Lancer depuis la racine : python -m unittest -v"""
import unittest

from app.db.database import PLAN_LIMITS, Database, max_keywords


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.init_schema()
        self.addCleanup(self.db.close)
        self.db.upsert_user(1, "sarah", "Sarah")


class TestUsers(DatabaseTestCase):
    def test_creation(self):
        user = self.db.get_user(1)
        self.assertEqual(user["username"], "sarah")
        self.assertEqual(user["plan"], "free")
        self.assertEqual(user["active"], 1)

    def test_utilisateur_inconnu(self):
        self.assertIsNone(self.db.get_user(999))

    def test_mise_a_jour_du_nom(self):
        self.db.upsert_user(1, "sarah_b", "Sarah B.")
        self.assertEqual(self.db.get_user(1)["username"], "sarah_b")
        self.assertEqual(self.db.stats()["users"], 1)

    def test_pause_puis_reactivation(self):
        self.db.set_active(1, False)
        self.assertEqual(self.db.get_user(1)["active"], 0)
        # Un simple upsert ne réactive pas...
        self.db.upsert_user(1, "sarah", "Sarah")
        self.assertEqual(self.db.get_user(1)["active"], 0)
        # ... mais /start (reactivate=True) oui.
        self.db.upsert_user(1, "sarah", "Sarah", reactivate=True)
        self.assertEqual(self.db.get_user(1)["active"], 1)

    def test_formule(self):
        self.assertTrue(self.db.set_plan(1, "premium"))
        self.assertEqual(self.db.get_user(1)["plan"], "premium")
        self.assertFalse(self.db.set_plan(999, "premium"))
        with self.assertRaises(ValueError):
            self.db.set_plan(1, "vip")


class TestKeywords(DatabaseTestCase):
    def test_ajout_liste_retrait(self):
        self.assertEqual(self.db.add_keyword(1, "stage informatique", "stage informatique"), "added")
        self.assertEqual(self.db.add_keyword(1, "bourse", "bourse"), "added")
        self.assertEqual(self.db.list_keywords(1), ["stage informatique", "bourse"])
        self.assertTrue(self.db.remove_keyword(1, "bourse"))
        self.assertFalse(self.db.remove_keyword(1, "bourse"))
        self.assertEqual(self.db.list_keywords(1), ["stage informatique"])

    def test_doublon_meme_forme_normalisee(self):
        self.assertEqual(self.db.add_keyword(1, "béjaïa", "bejaia"), "added")
        self.assertEqual(self.db.add_keyword(1, "BEJAIA", "bejaia"), "exists")
        self.assertEqual(len(self.db.list_keywords(1)), 1)

    def test_limite_gratuite_puis_premium(self):
        for i in range(PLAN_LIMITS["free"]):
            self.assertEqual(self.db.add_keyword(1, f"mot{i}", f"mot{i}"), "added")
        self.assertEqual(self.db.add_keyword(1, "de trop", "de trop"), "limit")
        self.db.set_plan(1, "premium")
        self.assertEqual(self.db.add_keyword(1, "de trop", "de trop"), "added")

    def test_les_utilisateurs_sont_independants(self):
        self.db.upsert_user(2, "karim", "Karim")
        self.db.add_keyword(1, "bourse", "bourse")
        self.assertEqual(self.db.list_keywords(2), [])
        self.assertEqual(self.db.add_keyword(2, "bourse", "bourse"), "added")

    def test_utilisateur_inconnu(self):
        with self.assertRaises(KeyError):
            self.db.add_keyword(999, "bourse", "bourse")

    def test_formule_inconnue_prend_la_limite_gratuite(self):
        self.assertEqual(max_keywords("n'importe quoi"), PLAN_LIMITS["free"])


class TestStats(DatabaseTestCase):
    def test_comptes(self):
        self.db.upsert_user(2, "karim", "Karim")
        self.db.set_active(2, False)
        self.db.add_keyword(1, "bourse", "bourse")
        self.assertEqual(self.db.stats(), {"users": 2, "active": 1, "keywords": 1})


if __name__ == "__main__":
    unittest.main()
