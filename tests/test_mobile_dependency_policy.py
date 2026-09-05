from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MobileDependencyPolicyTests(unittest.TestCase):
    def test_dependabot_does_not_group_platform_upgrades(self) -> None:
        policy = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

        self.assertIn("mobile-patches:", policy)
        self.assertNotIn("mobile-minor-and-patch:", policy)
        self.assertIn('dependency-name: "react-native"', policy)
        self.assertIn('dependency-name: "typescript"', policy)
        self.assertIn('"version-update:semver-minor"', policy)
        self.assertIn('"version-update:semver-major"', policy)

    def test_ci_enforces_the_expo_matrix_through_the_mobile_script(self) -> None:
        package = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertEqual(package["scripts"]["check:expo"], "expo install --check")
        self.assertIn("Validate Expo dependency matrix", workflow)
        self.assertIn("npm run check:expo", workflow)

    def test_high_severity_audit_uses_the_patched_metro_family(self) -> None:
        package = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "mobile" / "package-lock.json").read_text(encoding="utf-8"))
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertEqual(package["scripts"]["audit:high"], "npm audit --audit-level=high")
        self.assertEqual(
            package["overrides"],
            {
                "metro": "0.84.5",
                "metro-config": "0.84.5",
                "metro-transform-worker": "0.84.5",
            },
        )
        locked_packages = lock["packages"]
        self.assertEqual(locked_packages["node_modules/metro"]["version"], "0.84.5")
        self.assertEqual(locked_packages["node_modules/metro-config"]["version"], "0.84.5")
        self.assertEqual(locked_packages["node_modules/metro-transform-worker"]["version"], "0.84.5")
        self.assertNotIn("node_modules/image-size", locked_packages)
        self.assertIn("Audit high-severity Mobile dependencies", workflow)
        self.assertIn("npm run audit:high", workflow)


if __name__ == "__main__":
    unittest.main()
