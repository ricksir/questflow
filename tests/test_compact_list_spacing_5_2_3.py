from __future__ import annotations

import unittest
from pathlib import Path


class CompactListSpacing523Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.css = (cls.root / "web" / "styles.css").read_text(encoding="utf-8")

    def test_external_gap_is_reduced_and_centralized(self) -> None:
        self.assertIn("--inter-item-gap:", self.css)
        self.assertIn(".data-table--responsive tbody { gap: var(--inter-item-gap); }", self.css)
        self.assertIn(".data-table--coverage tbody { gap: var(--inter-item-gap); }", self.css)
        self.assertIn(".file-list,\n.alternatives-list { gap: var(--inter-item-gap); }", self.css)

    def test_dividers_replace_empty_space(self) -> None:
        self.assertIn("--inter-item-divider:", self.css)
        self.assertIn("border-bottom: 1px solid var(--inter-item-divider);", self.css)
        self.assertIn(".file-item:not(:last-child)", self.css)
        self.assertIn(".alternative-row:not(:last-child)", self.css)

    def test_internal_padding_rules_are_preserved(self) -> None:
        self.assertIn("padding: var(--space-2) var(--space-3); background: var(--surface-subtle)", self.css)
        self.assertIn("padding: var(--space-3); background: var(--surface-subtle); border-radius", self.css)
        self.assertIn("--list-row-height: 4.95rem;", self.css)

    def test_chrome_profile_is_versioned_to_523(self) -> None:
        source = (self.root / "desktop_runtime.py").read_text(encoding="utf-8")
        self.assertIn("chrome_runtime_5_4_0", source)
        self.assertNotIn("chrome_runtime_5_2_3", source)


if __name__ == "__main__":
    unittest.main()
