"""Tests de l'extraction de liens d'une page web. Lancer : python -m unittest -v"""
import unittest

from app.sources.html_links import decode_body, extract_links

BASE = "https://exemple.dz/annonces"

PAGE = """<html><head><script>var a = "<a href='/annonces/script'>lien dans un script assez long</a>";</script></head>
<body>
<a href="/annonces">Toutes les annonces de recrutement et de bourses</a>
<a href="/annonces/stage-informatique-2026">Offre de stage en informatique à Béjaïa</a>
<a href="/annonces/stage-informatique-2026#postuler">Offre de stage en informatique à Béjaïa</a>
<a href="/annonces/bourse-master">Bourse de master à l'étranger : candidatures ouvertes</a>
<a href="/contact">Nous contacter pour toute information</a>
<a href="/annonces/court">Court</a>
<a href="mailto:rh@exemple.dz">Écrire aux ressources humaines maintenant</a>
<a href="javascript:void(0)">Cliquer ici pour afficher le menu complet</a>
<a href="#haut">Retour en haut de la page web immédiatement</a>
<a href="https://autre-site.dz/annonces/offre-externe">Offre externe publiée sur un autre site web</a>
<a href="/annonces/emploi"><span>Emploi :</span> <b>technicien réseau</b> à Alger (CDI)</a>
</body></html>"""


class TestExtractLinks(unittest.TestCase):
    def test_avec_motif(self):
        items = extract_links(PAGE, BASE, "Site", link_pattern="/annonces/", min_title_len=25)
        self.assertEqual(
            [(i.title, i.url) for i in items],
            [
                ("Offre de stage en informatique à Béjaïa", "https://exemple.dz/annonces/stage-informatique-2026"),
                ("Bourse de master à l'étranger : candidatures ouvertes", "https://exemple.dz/annonces/bourse-master"),
                ("Offre externe publiée sur un autre site web", "https://autre-site.dz/annonces/offre-externe"),
                ("Emploi : technicien réseau à Alger (CDI)", "https://exemple.dz/annonces/emploi"),
            ],
        )
        self.assertTrue(all(i.source == "Site" for i in items))

    def test_sans_motif_garde_les_liens_assez_longs(self):
        urls = [i.url for i in extract_links(PAGE, BASE, "Site", None, 25)]
        self.assertIn("https://exemple.dz/contact", urls)
        self.assertNotIn("https://exemple.dz/annonces/court", urls)

    def test_seuil_de_longueur(self):
        urls = [i.url for i in extract_links(PAGE, BASE, "Site", "/annonces/", 5)]
        self.assertIn("https://exemple.dz/annonces/court", urls)

    def test_liens_dangereux_ou_internes_ignores(self):
        urls = [i.url for i in extract_links(PAGE, BASE, "Site", None, 5)]
        for url in urls:
            self.assertTrue(url.startswith("http"), url)
        self.assertNotIn("https://exemple.dz/annonces", urls)  # la page elle-même
        self.assertFalse(any("script" in u for u in urls))  # contenu d'un <script>

    def test_limite_du_nombre_de_liens(self):
        page = "".join(f'<a href="/a/{i}">Annonce numéro {i} très intéressante</a>' for i in range(150))
        self.assertEqual(len(extract_links(page, BASE, "Site")), 100)

    def test_page_vide_ou_cassee(self):
        self.assertEqual(extract_links("", BASE, "Site"), [])
        self.assertEqual(extract_links("<a href='/x'>texte <b>non fermé", BASE, "Site", None, 3)[0].url, "https://exemple.dz/x")


class TestDecode(unittest.TestCase):
    def test_encodage_declare(self):
        self.assertEqual(decode_body("café".encode("latin-1"), "iso-8859-1"), "café")

    def test_encodage_inconnu_ou_absent(self):
        self.assertEqual(decode_body("café".encode("utf-8"), "inconnu-xyz"), "café")
        self.assertEqual(decode_body("café".encode("utf-8"), None), "café")

    def test_octets_invalides_sans_exception(self):
        self.assertIn("�", decode_body(b"\xff\xfe abc", "utf-8"))


if __name__ == "__main__":
    unittest.main()
