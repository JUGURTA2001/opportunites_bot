"""Tests de la lecture des flux RSS/Atom. Lancer depuis la racine : python -m unittest -v"""
import unittest

from app.sources.errors import FeedError
from app.sources.models import Item, canonical_url, is_http_url
from app.sources.rss import clean_text, parse_feed

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Flux</title>
<item><title>Bourse d'excellence &amp; mobilité</title>
  <link>https://exemple.dz/bourse-1?utm_source=rss#haut</link>
  <description><![CDATA[<p>Candidatures ouvertes jusqu'au <b>30 novembre</b>.</p>]]></description></item>
<item><title>Stage informatique à Béjaïa</title><link>https://exemple.dz/stage-2</link>
  <description>Stage de 3 mois</description></item>
<item><title>Stage informatique à Béjaïa</title><link>https://exemple.dz/stage-2?utm_medium=x</link></item>
<item><title></title><link>https://exemple.dz/sans-titre</link></item>
<item><title>Lien dangereux</title><link>javascript:alert(1)</link></item>
<item><title>Sans lien</title></item>
</channel></rss>""".encode("utf-8")

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Annonces</title>
<entry><title>Concours de recrutement</title>
  <link rel="self" href="https://exemple.dz/flux/1"/>
  <link rel="alternate" href="https://exemple.dz/concours-1"/>
  <summary>Ouverture du concours</summary></entry>
<entry><title type="html">Emploi &amp;amp; stages</title>
  <link href="https://exemple.dz/emploi-2"/><content>Offres &lt;b&gt;du mois&lt;/b&gt;</content></entry>
</feed>"""


class TestRss(unittest.TestCase):
    def test_flux_rss_valide(self):
        items = parse_feed(RSS, "Flux")
        self.assertEqual([i.title for i in items], ["Bourse d'excellence & mobilité", "Stage informatique à Béjaïa"])
        self.assertEqual(items[0].summary, "Candidatures ouvertes jusqu'au 30 novembre .")
        self.assertEqual(items[0].source, "Flux")

    def test_doublon_ignore_malgre_les_parametres_de_suivi(self):
        urls = [i.url for i in parse_feed(RSS, "Flux")]
        self.assertEqual(urls.count("https://exemple.dz/stage-2"), 1)

    def test_identifiant_stable_sans_suivi_ni_fragment(self):
        first = parse_feed(RSS, "Flux")[0]
        clean = Item("Flux", first.title, "https://exemple.dz/bourse-1")
        self.assertEqual(first.item_id, clean.item_id)

    def test_elements_invalides_ignores(self):
        titles = [i.title for i in parse_feed(RSS, "Flux")]
        for bad in ("Lien dangereux", "Sans lien"):
            self.assertNotIn(bad, titles)

    def test_atom(self):
        items = parse_feed(ATOM, "Annonces")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, "https://exemple.dz/concours-1")  # rel="alternate"
        self.assertEqual(items[0].summary, "Ouverture du concours")
        self.assertEqual(items[1].url, "https://exemple.dz/emploi-2")
        self.assertEqual(items[1].summary, "Offres du mois")

    def test_texte_et_octets(self):
        self.assertEqual(len(parse_feed(RSS.decode("utf-8"), "Flux")), 2)

    def test_encodage_declare(self):
        xml = (
            '<?xml version="1.0" encoding="ISO-8859-1"?><rss><channel><item>'
            "<title>Café étudiant</title><link>https://exemple.dz/cafe</link></item></channel></rss>"
        ).encode("latin-1")
        self.assertEqual(parse_feed(xml, "x")[0].title, "Café étudiant")

    def test_flux_vide(self):
        self.assertEqual(parse_feed(b"<rss><channel><title>Vide</title></channel></rss>", "x"), [])


class TestRssErreurs(unittest.TestCase):
    def test_page_html_refusee(self):
        with self.assertRaises(FeedError):
            parse_feed(b"<html><body><p>Oups</p></body></html>", "x")

    def test_xml_casse(self):
        with self.assertRaises(FeedError):
            parse_feed(b"<rss><channel><item>", "x")

    def test_contenu_vide(self):
        with self.assertRaises(FeedError):
            parse_feed(b"", "x")

    def test_expansion_d_entites_refusee(self):
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            b"<rss><channel><item><title>&b;</title><link>https://x.dz/1</link></item></channel></rss>"
        )
        with self.assertRaises(FeedError):
            parse_feed(bomb, "x")
        with self.assertRaises(FeedError):
            parse_feed(bomb.decode("utf-8"), "x")


class TestOutils(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("<p>Hello&nbsp;<b>monde</b> &amp; tous</p>", 100), "Hello monde & tous")
        self.assertEqual(clean_text(None, 10), "")
        self.assertEqual(len(clean_text("a" * 1000, 50)), 50)

    def test_canonical_url(self):
        self.assertEqual(
            canonical_url("HTTPS://Exemple.DZ/a?utm_source=x&id=3&utm_medium=y#frag"),
            "https://exemple.dz/a?id=3",
        )

    def test_is_http_url(self):
        self.assertTrue(is_http_url("https://exemple.dz/x"))
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "mailto:a@b.dz", "/relatif", "https://"):
            with self.subTest(bad=bad):
                self.assertFalse(is_http_url(bad))


if __name__ == "__main__":
    unittest.main()
