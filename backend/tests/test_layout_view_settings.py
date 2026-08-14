"""布局级共享晶圆图设置测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import store


class LayoutViewSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_data_dir = store.DATA_DIR
        self._old_db_path = store.DB_PATH
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        store.DATA_DIR = Path(self._tmp.name)
        store.DB_PATH = store.DATA_DIR / "test.db"
        store.init_db()

    def tearDown(self) -> None:
        store.DATA_DIR = self._old_data_dir
        store.DB_PATH = self._old_db_path
        self._tmp.cleanup()

    def test_missing_layout_uses_automatic_defaults(self) -> None:
        self.assertEqual(
            store.get_layout_view_settings("layout-a"),
            {
                "layout_id": "layout-a",
                "wafer_scale": 1.0,
                "wafer_offset_x": 0.0,
                "wafer_offset_y": 0.0,
            },
        )

    def test_saved_settings_are_isolated_by_layout_and_can_be_overwritten(self) -> None:
        store.save_layout_view_settings(
            "layout-a",
            {"wafer_scale": 0.85, "wafer_offset_x": 0.5, "wafer_offset_y": -0.25},
        )
        store.save_layout_view_settings(
            "layout-b",
            {"wafer_scale": 1.15, "wafer_offset_x": -1.0, "wafer_offset_y": 0.75},
        )
        store.save_layout_view_settings(
            "layout-a",
            {"wafer_scale": 0.9, "wafer_offset_x": 0.25, "wafer_offset_y": 0.0},
        )

        self.assertEqual(store.get_layout_view_settings("layout-a")["wafer_scale"], 0.9)
        self.assertEqual(store.get_layout_view_settings("layout-a")["wafer_offset_x"], 0.25)
        self.assertEqual(store.get_layout_view_settings("layout-b")["wafer_scale"], 1.15)
        self.assertEqual(store.get_layout_view_settings("layout-b")["wafer_offset_x"], -1.0)


if __name__ == "__main__":
    unittest.main()
