"""Tests du cycle d'alertes et de la planification (sans réseau ni Telegram).

Lancer depuis la racine : python -m unittest -v
"""
import asyncio
import unittest
from unittest.mock import patch

from app.db.database import Database
from app.services import alerts
from app.services.alerts import CycleReport, CycleRunner, UserBlocked
from app.services.scheduler import run_forever
from app.sources.errors import FetchError
from app.sources.models import Source

FLUX = Source("Flux", "rss", "https://flux.test/rss")


def feed(*entries) -> bytes:
    """Fabrique un flux RSS à partir de tuples (titre, adresse) ou (titre, adresse, résumé)."""
    items = ""
    for entry in entries:
        title, url, *rest = entry
        summary = rest[0] if rest else ""
        items += f"<item><title>{title}</title><link>{url}</link><description>{summary}</description></item>"
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>{items}</channel></rss>'.encode()


class FakeFetcher:
    def __init__(self):
        self.pages: dict[str, bytes | Exception] = {}
        self.robots_ok = True

    async def get(self, url):
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return value, None

    async def allowed(self, url):
        return self.robots_ok


class Outbox:
    """Remplace l'envoi Telegram : garde les messages, simule blocages et pannes."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self.blocked: set[int] = set()
        self.failing: set[int] = set()

    async def __call__(self, user_id, text):
        if user_id in self.blocked:
            raise UserBlocked("bot bloqué")
        if user_id in self.failing:
            raise RuntimeError("réseau indisponible")
        self.sent.append((user_id, text))

    def to(self, user_id):
        return [text for uid, text in self.sent if uid == user_id]


class AlertsTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.object(alerts, "SEND_DELAY_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.db = Database(":memory:")
        self.db.init_schema()
        self.addCleanup(self.db.close)
        for uid in (1, 2, 3):
            self.db.upsert_user(uid, f"u{uid}", f"U{uid}")
        self.db.add_keyword(1, "bourse", "bourse")
        self.db.add_keyword(2, "stage informatique", "stage informatique")
        self.db.add_keyword(3, "bourse", "bourse")
        self.db.set_active(3, False)  # utilisateur en pause

        self.fetcher = FakeFetcher()
        self.outbox = Outbox()
        self.sources = [FLUX]
        self.runner = CycleRunner(self.db, self.sources, self.fetcher, self.outbox)

    def serve(self, *entries):
        self.fetcher.pages[FLUX.url] = feed(*entries)

    async def baseline(self):
        """Premier passage : mémorise une offre existante sans rien envoyer."""
        self.serve(("Offre ancienne", "https://a.dz/0"))
        return await self.runner.run()


class TestCycle(AlertsTestCase):
    async def test_premier_passage_sans_alerte(self):
        report = await self.baseline()
        self.assertEqual((report.baselined, report.new_items, report.alerts_sent), (1, 0, 0))
        self.assertEqual(self.outbox.sent, [])
        self.assertTrue(self.db.is_source_known("Flux"))

    async def test_nouvelles_offres_envoyees_aux_bons_abonnes(self):
        await self.baseline()
        self.serve(
            ("Offre ancienne", "https://a.dz/0"),
            ("Bourse de master en France", "https://a.dz/1"),
            ("Stage informatique à Béjaïa", "https://a.dz/2"),
            ("Concours de dessin", "https://a.dz/3"),
        )
        report = await self.runner.run()
        self.assertEqual((report.new_items, report.alerts_sent), (3, 2))
        self.assertEqual(len(self.outbox.to(1)), 1)
        self.assertIn("Bourse de master en France", self.outbox.to(1)[0])
        self.assertIn("https://a.dz/1", self.outbox.to(1)[0])
        self.assertIn("Mot-clé : bourse", self.outbox.to(1)[0])
        self.assertIn("Source : Flux", self.outbox.to(1)[0])
        self.assertEqual(len(self.outbox.to(2)), 1)
        self.assertIn("Stage informatique", self.outbox.to(2)[0])
        self.assertEqual(self.outbox.to(3), [])  # en pause : rien

    async def test_la_recherche_porte_aussi_sur_le_resume(self):
        await self.baseline()
        self.serve(("Annonce importante", "https://a.dz/9", "Une bourse de recherche est ouverte"))
        await self.runner.run()
        self.assertEqual(len(self.outbox.to(1)), 1)

    async def test_pas_de_doublon_aux_cycles_suivants(self):
        await self.baseline()
        self.serve(("Bourse d'excellence", "https://a.dz/1"))
        await self.runner.run()
        await self.runner.run()
        await self.runner.run()
        self.assertEqual(len(self.outbox.to(1)), 1)

    async def test_meme_offre_avec_parametres_de_suivi_pas_renvoyee(self):
        await self.baseline()
        self.serve(("Bourse d'excellence", "https://a.dz/1"))
        await self.runner.run()
        self.serve(("Bourse d'excellence", "https://a.dz/1?utm_source=newsletter"))
        await self.runner.run()
        self.assertEqual(len(self.outbox.to(1)), 1)

    async def test_utilisateur_qui_a_bloque_le_bot_est_desactive(self):
        await self.baseline()
        self.outbox.blocked = {1}
        self.serve(("Bourse et stage informatique", "https://a.dz/1"))
        await self.runner.run()
        self.assertEqual(self.db.get_user(1)["active"], 0)
        self.assertEqual(len(self.outbox.to(2)), 1)  # les autres reçoivent quand même

    async def test_echec_temporaire_puis_reprise_sans_doublon(self):
        await self.baseline()
        self.outbox.failing = {1}
        self.serve(("Bourse et stage informatique", "https://a.dz/1"))
        with self.assertLogs("app.services.alerts", level="ERROR"):
            await self.runner.run()
        self.assertEqual(len(self.outbox.to(2)), 1)
        self.assertEqual(self.outbox.to(1), [])
        self.assertEqual(len(self.db.pending_items()), 1)  # reste en attente

        self.outbox.failing = set()
        await self.runner.run()
        self.assertEqual(len(self.outbox.to(1)), 1)  # rattrapé
        self.assertEqual(len(self.outbox.to(2)), 1)  # pas de doublon
        self.assertEqual(self.db.pending_items(), [])


class TestRobustesse(AlertsTestCase):
    async def test_une_source_en_panne_n_arrete_pas_les_autres(self):
        autre = Source("Autre", "rss", "https://autre.test/rss")
        self.runner = CycleRunner(self.db, [FLUX, autre], self.fetcher, self.outbox)
        self.fetcher.pages[FLUX.url] = FetchError("HTTP 500", status=500)
        self.fetcher.pages[autre.url] = feed(("Offre", "https://autre.test/1"))
        report = await self.runner.run()
        self.assertEqual((report.sources_ok, report.sources_failed), (1, 1))
        self.assertIn("Flux : HTTP 500", report.errors[0])
        self.assertTrue(self.db.is_source_known("Autre"))

    async def test_contenu_invalide_signale(self):
        self.fetcher.pages[FLUX.url] = b"<html>pas un flux</html>"
        report = await self.runner.run()
        self.assertEqual(report.sources_failed, 1)
        self.assertIn("RSS", report.errors[0])

    async def test_robots_txt_respecte_pour_les_pages_html(self):
        page = Source("Site", "html", "https://site.test/annonces")
        self.runner = CycleRunner(self.db, [page], self.fetcher, self.outbox)
        self.fetcher.robots_ok = False
        report = await self.runner.run()
        self.assertEqual(report.sources_failed, 1)
        self.assertIn("robots.txt", report.errors[0])

    async def test_page_html_lue_quand_robots_autorise(self):
        page = Source("Site", "html", "https://site.test/annonces", "/annonces/", 20)
        self.runner = CycleRunner(self.db, [page], self.fetcher, self.outbox)
        self.fetcher.pages[page.url] = (
            b'<a href="/annonces/bourse-1">Bourse nationale pour les etudiants</a>'
        )
        report = await self.runner.run()
        self.assertEqual((report.sources_ok, report.baselined), (1, 1))

    async def test_inondation_ignoree(self):
        await self.baseline()
        self.serve(*[(f"Bourse numéro {i}", f"https://a.dz/b{i}") for i in range(alerts.MAX_NEW_PER_SOURCE + 1)])
        report = await self.runner.run()
        self.assertEqual((report.new_items, report.alerts_sent), (0, 0))
        self.assertIn("ignorées", report.errors[0])
        self.assertEqual(self.db.pending_items(), [])
        self.assertEqual(self.outbox.sent, [])

    async def test_limite_par_utilisateur_et_message_de_synthese(self):
        await self.baseline()
        total = alerts.MAX_ALERTS_PER_USER_PER_CYCLE + 2
        self.serve(*[(f"Bourse numéro {i}", f"https://a.dz/b{i}") for i in range(total)])
        report = await self.runner.run()
        self.assertEqual(report.alerts_sent, alerts.MAX_ALERTS_PER_USER_PER_CYCLE)
        messages = self.outbox.to(1)
        self.assertEqual(len(messages), alerts.MAX_ALERTS_PER_USER_PER_CYCLE + 1)
        self.assertIn("2 autres offres", messages[-1])

    async def test_aucune_source(self):
        self.runner = CycleRunner(self.db, [], self.fetcher, self.outbox)
        report = await self.runner.run()
        self.assertEqual((report.sources_ok, report.alerts_sent), (0, 0))

    async def test_pas_de_chevauchement_de_cycles(self):
        gate = asyncio.Event()

        class Lent(FakeFetcher):
            async def get(self, url):
                await gate.wait()
                return feed(("Offre", "https://a.dz/1")), None

        self.runner = CycleRunner(self.db, [FLUX], Lent(), self.outbox)
        premier = asyncio.create_task(self.runner.run())
        await asyncio.sleep(0.01)
        self.assertIsNone(await self.runner.run())  # déjà en cours
        gate.set()
        self.assertIsNotNone(await premier)
        self.assertIsNotNone(await self.runner.run())  # de nouveau possible


class TestRapport(unittest.TestCase):
    def test_texte_du_rapport(self):
        report = CycleReport(sources_ok=2, sources_failed=1, baselined=5, new_items=3, alerts_sent=4,
                             errors=[f"Source {i} : HTTP 500" for i in range(7)])
        text = report.format()
        self.assertIn("Sources lues : 2 (échecs : 1)", text)
        self.assertIn("Nouvelles offres : 3 (+5 mémorisées au premier passage)", text)
        self.assertIn("Alertes envoyées : 4", text)
        self.assertIn("• Source 0 : HTTP 500", text)
        self.assertIn("et 2 autres", text)

    def test_rapport_sans_probleme(self):
        self.assertNotIn("Problèmes", CycleReport().format())


class TestScheduler(unittest.IsolatedAsyncioTestCase):
    async def test_repete_les_cycles_et_survit_aux_erreurs(self):
        class Runner:
            def __init__(self):
                self.calls = 0

            async def run(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("panne ponctuelle")

        runner = Runner()
        with self.assertLogs("app.services.scheduler", level="ERROR"):
            task = asyncio.create_task(run_forever(runner, 0.01))
            for _ in range(200):
                if runner.calls >= 3:
                    break
                await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertGreaterEqual(runner.calls, 3)


if __name__ == "__main__":
    unittest.main()
