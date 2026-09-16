from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from app_shared import TAXONOMY_PATH
from web_api import QuestFlowWebApi
from web_server import QuestFlowLocalServer


class StudioV1LegislationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.api = QuestFlowWebApi(
            self.root / "questflow.sqlite",
            config={},
            config_path=self.root / "config.json",
            taxonomy_path=TAXONOMY_PATH,
        )
        self.api.bootstrap()
        self.payload = {
            "canonical_key": "CTN_ART_151_TESTE",
            "title": "CTN art. 151 · versão de teste",
            "subject": "Direito Tributário",
            "source_label": "Fonte oficial de teste",
            "source_url": "https://example.test/ctn-151",
            "effective_from": "2026-01-01",
            "effective_to": "",
            "text_content": "A moratória suspende a exigibilidade do crédito tributário.",
        }

    def tearDown(self) -> None:
        self.api.shutdown()
        self.temp.cleanup()

    def test_contract_exposes_legislation_operations_with_correct_mutability(self) -> None:
        definitions = {
            item["name"]: item
            for item in self.api.get_studio_contract_v1()["operations"]
        }
        self.assertEqual(
            definitions["editorial.legislation.versions.upsert"]["module"],
            "editorial_bank",
        )
        self.assertTrue(definitions["editorial.legislation.versions.upsert"]["mutating"])
        self.assertEqual(
            definitions["editorial.legislation.versions.resolve"]["module"],
            "editorial_bank",
        )
        self.assertFalse(definitions["editorial.legislation.versions.resolve"]["mutating"])

    def test_dispatcher_matches_existing_legislation_facades(self) -> None:
        studio_upsert = self.api.dispatch_studio_v1(
            "editorial.legislation.versions.upsert",
            self.payload,
        )
        self.assertTrue(studio_upsert["ok"])
        legacy_resolved = self.api.resolve_legislation_version(
            self.payload["canonical_key"],
            "2026-08-13",
        )
        self.assertEqual(studio_upsert["data"]["version"], legacy_resolved["version"])
        assert self.api.engines is not None
        self.assertEqual(
            studio_upsert["data"]["summary"],
            self.api.engines.editorial.legislation_summary(),
        )

        studio_resolved = self.api.dispatch_studio_v1(
            "editorial.legislation.versions.resolve",
            {
                "canonical_key": self.payload["canonical_key"],
                "reference_date": "2026-08-13",
            },
        )
        self.assertTrue(studio_resolved["ok"])
        self.assertEqual(
            studio_resolved["data"],
            {"version": legacy_resolved["version"]},
        )

    def test_resolve_requires_key_and_reference_date(self) -> None:
        for payload in ({}, {"canonical_key": self.payload["canonical_key"]}):
            with self.subTest(payload=payload):
                result = self.api.dispatch_studio_v1(
                    "editorial.legislation.versions.resolve",
                    payload,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "validation_error")
                self.assertEqual(result["status"], 400)

    def test_authenticated_http_routes_upsert_and_resolve_legislation(self) -> None:
        server = QuestFlowLocalServer(
            self.api,
            Path(__file__).resolve().parents[1] / "web",
            preferred_port=0,
        )
        server.start()
        try:
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/editorial/legislation/versions",
                data=json.dumps(self.payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-QuestFlow-Token": server.token,
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                created = json.loads(response.read().decode("utf-8"))
            self.assertTrue(created["ok"])
            self.assertEqual(created["operation"], "editorial.legislation.versions.upsert")
            self.assertEqual(created["contract"], "questflow.studio.v1")

            query = urllib.parse.urlencode({
                "canonical_key": self.payload["canonical_key"],
                "reference_date": "2026-08-13",
            })
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/studio/editorial/legislation/versions/resolve?{query}",
                headers={"X-QuestFlow-Token": server.token},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                resolved = json.loads(response.read().decode("utf-8"))
            self.assertTrue(resolved["ok"])
            self.assertEqual(resolved["operation"], "editorial.legislation.versions.resolve")
            self.assertEqual(
                resolved["data"]["version"]["canonical_key"],
                self.payload["canonical_key"],
            )
        finally:
            server.stop()

    def test_frontend_uses_studio_transport_with_legacy_fallbacks(self) -> None:
        javascript = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("'editorial/legislation/versions'", javascript)
        self.assertIn("'create_legislation_version'", javascript)
        self.assertIn(
            "`editorial/legislation/versions/resolve?${query.toString()}`",
            javascript,
        )
        self.assertIn("'resolve_legislation_version'", javascript)
        for method in ("create_legislation_version", "resolve_legislation_version"):
            self.assertNotIn(f"bridge.call('{method}'", javascript)


if __name__ == "__main__":
    unittest.main()
