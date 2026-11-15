"""Tests du chargement de sources.json et de robots.txt. Lancer : python -m unittest -v"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.sources.registry import SourceConfigError, load_sources
from app.sources.robots import robots_allows


class TestRegistry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "sources.json")

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return self.path

    def check_error(self, data, fragment):
        with self.assertRaises(SourceConfigError) as ctx:
            load_sources(self.write(data))
        self.assertIn(fragment, str(ctx.exception))

    def test_valide_et_sources_desactivees_ignorees(self):
        sources = load_sources(self.write([
            {"name": "A", "type": "rss", "url": "https://a.dz/rss"},
            {"name": "B", "type": "html", "url": "https://b.dz/", "link_pattern": "/annonces/", "min_title_len": 30},
            {"name": "C", "type": "rss", "url": "https://c.dz/rss", "enabled": False},
        ]))
        self.assertEqual([s.name for s in sources], ["A", "B"])
        self.assertEqual(sources[1].link_pattern, "/annonces/")
        self.assertEqual(sources[1].min_title_len, 30)
        self.assertEqual(sources[0].min_title_len, 25)

    def test_fichier_absent(self):
        with self.assertRaises(FileNotFoundError):
            load_sources(os.path.join(os.path.dirname(self.path), "absent.json"))

    def test_erreurs(self):
        ok = {"name": "A", "type": "rss", "url": "https://a.dz/rss"}
        self.check_error("{pas du json", "JSON invalide")
        self.check_error({"name": "A"}, "liste")
        self.check_error(["texte"], "objet attendu")
        self.check_error([{**ok, "name": ""}], "name")
        self.check_error([ok, ok], "déjà utilisé")
        self.check_error([{**ok, "type": "xml"}], "type")
        self.check_error([{**ok, "url": "ftp://a.dz"}], "url")
        self.check_error([{**ok, "url": "javascript:alert(1)"}], "url")
        self.check_error([{**ok, "link_pattern": "["}], "link_pattern")
        self.check_error([{**ok, "min_title_len": 0}], "min_title_len")
        self.check_error([{**ok, "min_title_len": True}], "min_title_len")
        self.check_error([{**ok, "enabled": "oui"}], "enabled")

    def test_fichier_fourni_avec_le_projet(self):
        shipped = Path(__file__).resolve().parent.parent / "sources.json"
        sources = load_sources(str(shipped))
        self.assertGreaterEqual(len(sources), 1)
        self.assertTrue(all(s.type in ("rss", "html") for s in sources))


class TestRobots(unittest.TestCase):
    AGENT = "OpportunitesEtudiantsBot/1.0"

    def test_tout_autorise_si_vide(self):
        self.assertTrue(robots_allows("", "https://a.dz/annonces/1", self.AGENT))

    def test_chemin_interdit(self):
        txt = "User-agent: *\nDisallow: /prive/\n"
        self.assertFalse(robots_allows(txt, "https://a.dz/prive/page", self.AGENT))
        self.assertTrue(robots_allows(txt, "https://a.dz/annonces/1", self.AGENT))

    def test_tout_interdit(self):
        self.assertFalse(robots_allows("User-agent: *\nDisallow: /\n", "https://a.dz/", self.AGENT))

    def test_regle_specifique_au_bot(self):
        txt = "User-agent: OpportunitesEtudiantsBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
        self.assertFalse(robots_allows(txt, "https://a.dz/x", self.AGENT))
        self.assertTrue(robots_allows(txt, "https://a.dz/x", "AutreBot"))


if __name__ == "__main__":
    unittest.main()
