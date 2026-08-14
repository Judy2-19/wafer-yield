from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import layout_store


ROOT = Path(__file__).resolve().parents[2]
SF_DR8 = ROOT / "examples" / "SF_DR8.txt"


class LayoutTemplateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_data_dir = layout_store.DATA_DIR
        self._old_layout_path = layout_store.LAYOUT_PATH
        self._old_template_dir = getattr(layout_store, "TEMPLATE_DIR", None)
        self._old_current_id_path = getattr(layout_store, "CURRENT_ID_PATH", None)
        self._old_current = layout_store._current
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        layout_store.DATA_DIR = Path(self._tmp.name)
        layout_store.LAYOUT_PATH = layout_store.DATA_DIR / "current_layout.json"
        layout_store.TEMPLATE_DIR = layout_store.DATA_DIR / "layout_templates"
        layout_store.CURRENT_ID_PATH = layout_store.DATA_DIR / "current_layout_id.txt"
        layout_store._current = None

    def tearDown(self) -> None:
        layout_store.DATA_DIR = self._old_data_dir
        layout_store.LAYOUT_PATH = self._old_layout_path
        if self._old_template_dir is not None:
            layout_store.TEMPLATE_DIR = self._old_template_dir
        if self._old_current_id_path is not None:
            layout_store.CURRENT_ID_PATH = self._old_current_id_path
        layout_store._current = self._old_current
        self._tmp.cleanup()

    def test_upload_persists_named_templates_and_selection(self) -> None:
        text = SF_DR8.read_text(encoding="utf-8")
        first = layout_store.set_layout_from_text(text, filename="SF_DR8.txt")
        changed = text.replace("\t41\n", "\t40\n", 1)
        second = layout_store.set_layout_from_text(changed, filename="Customer_A.txt")

        templates = layout_store.list_layout_templates()
        self.assertEqual({item["layout_id"] for item in templates}, {first["layout_id"], second["layout_id"]})
        self.assertEqual(layout_store.get_layout()["layout_id"], second["layout_id"])
        self.assertEqual(sum(1 for item in templates if item["current"]), 1)

        selected = layout_store.select_layout_template(first["layout_id"])
        self.assertEqual(selected["layout_id"], first["layout_id"])
        layout_store._current = None
        self.assertEqual(layout_store.get_layout()["layout_id"], first["layout_id"])

    def test_same_content_with_different_filenames_creates_separate_templates(self) -> None:
        text = SF_DR8.read_text(encoding="utf-8")

        first = layout_store.set_layout_from_text(text, filename="SF_DR8.txt")
        second = layout_store.set_layout_from_text(text, filename="客户二号图.txt")
        repeated = layout_store.set_layout_from_text(text, filename="客户二号图.txt")
        updated = layout_store.set_layout_from_text(
            text.replace("\t41\n", "\t40\n", 1), filename="客户二号图.txt"
        )

        templates = layout_store.list_layout_templates()
        self.assertNotEqual(first["layout_id"], second["layout_id"])
        self.assertEqual(repeated["layout_id"], second["layout_id"])
        self.assertEqual(updated["layout_id"], second["layout_id"])
        self.assertEqual(len(templates), 2)
        self.assertEqual({item["name"] for item in templates}, {"SF_DR8", "客户二号图"})

    def test_rename_and_delete_current_template_switches_to_remaining(self) -> None:
        text = SF_DR8.read_text(encoding="utf-8")
        first = layout_store.set_layout_from_text(text, filename="SF_DR8.txt")
        second = layout_store.set_layout_from_text(text.replace("\t41\n", "\t40\n", 1), filename="B.txt")
        layout_store.select_layout_template(first["layout_id"])

        renamed = layout_store.rename_layout_template(first["layout_id"], "量产布局")
        self.assertEqual(renamed["name"], "量产布局")

        current = layout_store.delete_layout_template(first["layout_id"])
        self.assertEqual(current["layout_id"], second["layout_id"])
        self.assertEqual(len(layout_store.list_layout_templates()), 1)

    def test_deleting_the_last_template_clears_the_current_layout(self) -> None:
        text = SF_DR8.read_text(encoding="utf-8")
        only = layout_store.set_layout_from_text(text, filename="唯一模板.txt")

        current = layout_store.delete_layout_template(only["layout_id"])

        self.assertIsNone(current)
        self.assertEqual(layout_store.list_layout_templates(), [])
        self.assertIsNone(layout_store.get_layout())

    def test_legacy_current_layout_is_migrated_into_template_library(self) -> None:
        text = SF_DR8.read_text(encoding="utf-8")
        layout = layout_store.parse_layout_text(text, filename="Legacy.txt")
        layout_store.LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        layout_store.LAYOUT_PATH.write_text(__import__("json").dumps(layout, ensure_ascii=False), encoding="utf-8")
        layout_store._current = None

        templates = layout_store.list_layout_templates()
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["name"], "Legacy")
        self.assertTrue(templates[0]["current"])


if __name__ == "__main__":
    unittest.main()
