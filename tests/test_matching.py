"""Tests du nettoyage des mots-clés et de la recherche. Lancer : python -m unittest -v"""
import unittest

from app.services.matching import clean_keyword, matches, normalize


class TestNormalize(unittest.TestCase):
    def test_accents_casse_ponctuation(self):
        self.assertEqual(normalize("  Stage d'Été — Béjaïa !! "), "stage d ete bejaia")


class TestCleanKeyword(unittest.TestCase):
    def test_affichage_et_forme_normalisee(self):
        self.assertEqual(clean_keyword("  Stage   Informatique "), ("stage informatique", "stage informatique"))
        self.assertEqual(clean_keyword("Béjaïa"), ("béjaïa", "bejaia"))

    def test_trop_court(self):
        for raw in ["", " ", "a", "!"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                clean_keyword(raw)

    def test_trop_long(self):
        with self.assertRaises(ValueError):
            clean_keyword("a" * 41)
        self.assertEqual(clean_keyword("a" * 40)[1], "a" * 40)


class TestMatches(unittest.TestCase):
    def test_mot_present(self):
        self.assertTrue(matches("Bourse d'excellence pour le Master", "bourse"))

    def test_accents_ignores(self):
        self.assertTrue(matches("Offre de stage à Béjaïa", "bejaia"))

    def test_tous_les_mots_sont_requis(self):
        self.assertTrue(matches("Stage en informatique à Alger", "stage informatique"))
        self.assertFalse(matches("Stage en comptabilité", "stage informatique"))

    def test_debut_de_mot_a_partir_de_4_lettres(self):
        self.assertTrue(matches("Plusieurs stages proposés", "stage"))
        self.assertTrue(matches("Poste en informatique", "info"))

    def test_mots_courts_exacts_seulement(self):
        self.assertFalse(matches("Voyage en Italie", "it"))
        self.assertTrue(matches("Poste IT confirmé", "it"))

    def test_pas_de_faux_positif(self):
        self.assertFalse(matches("Concours de dessin", "bourse"))
        self.assertFalse(matches("Texte quelconque", ""))


if __name__ == "__main__":
    unittest.main()
