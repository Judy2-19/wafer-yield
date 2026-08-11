"""布局 TSV 解析与 Shot 坐标匹配测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.layout_tsv import LayoutParseError, lookup_shot_xy, parse_layout_text

ROOT = Path(__file__).resolve().parents[2]
SF_DR8 = ROOT / "examples" / "SF_DR8.txt"


class LayoutTsvTests(unittest.TestCase):
    def test_parse_sf_dr8(self) -> None:
        text = SF_DR8.read_text(encoding="utf-8")
        layout = parse_layout_text(text, filename="SF_DR8.txt")
        self.assertEqual(len(layout["shots"]), 60)
        self.assertEqual(len(layout["sites"]), 17)
        self.assertEqual(len(layout["test_keys"]), 1)
        self.assertEqual(layout["test_keys"][0], {"row": 2, "col": 1})
        self.assertEqual(layout["site_grid"]["rows"], 6)
        self.assertEqual(layout["site_grid"]["cols"], 3)
        # Shot 82：Level1 row=1,col=7 → 图谱 (x=7,y=1)，不是旧公式 (8,2)
        self.assertEqual(lookup_shot_xy(layout, "82"), (7, 1))
        self.assertEqual(lookup_shot_xy(layout, 56), (4, 5))
        self.assertEqual(layout["map_grid"]["min_x"], 0)
        self.assertEqual(layout["map_grid"]["max_x"], 9)
        self.assertEqual(layout["map_grid"]["min_y"], 0)
        self.assertEqual(layout["map_grid"]["max_y"], 6)
        # Die 网格含 Test Key 空位
        empties = [c for c in layout["die_grid"] if c.get("empty")]
        self.assertEqual(len(empties), 1)
        self.assertEqual(empties[0]["row"], 2)
        self.assertEqual(empties[0]["col"], 1)
        self.assertIn("0202", layout["die_serials"])
        self.assertNotIn("0203", layout["die_serials"])

    def test_reject_missing_level1(self) -> None:
        text = (
            "level\treticle(struct).row\treticle(struct).col\treticle(struct).prober\treticle(struct).custom\n"
            "2\t0\t0\tSN0101\tSN0101\n"
        )
        with self.assertRaises(LayoutParseError):
            parse_layout_text(text)

    def test_reject_duplicate_custom(self) -> None:
        text = (
            "level\treticle(struct).row\treticle(struct).col\treticle(struct).prober\treticle(struct).custom\n"
            "1\t0\t0\t\t11\n"
            "1\t0\t1\t\t11\n"
            "2\t0\t0\tSN0101\tSN0101\n"
        )
        with self.assertRaises(LayoutParseError):
            parse_layout_text(text)


if __name__ == "__main__":
    unittest.main()
