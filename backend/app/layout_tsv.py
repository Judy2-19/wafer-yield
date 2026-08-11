"""按 FIELD_SPEC 解析 Shot 布局 TSV（Level1 Shot + Level2 小格模板）。"""

from __future__ import annotations

import re
from typing import Any


REQUIRED_HEADERS = (
    "level",
    "reticle(struct).row",
    "reticle(struct).col",
    "reticle(struct).prober",
    "reticle(struct).custom",
)


class LayoutParseError(ValueError):
    """布局文件格式或校验失败。"""


def _unquote(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == '"' and trimmed[-1] == '"':
        return trimmed[1:-1].replace('""', '"')
    return trimmed


def _integer(value: str, name: str, line_no: int) -> int:
    text = (value or "").strip()
    if not re.fullmatch(r"-?\d+", text):
        raise LayoutParseError(f"第 {line_no} 行：{name} 必须是整数，实际为 {value!r}")
    return int(text)


def _normalize_custom(value: str) -> str:
    return (value or "").strip()


def _serial_from_custom(custom: str) -> str | None:
    """SN0101 / 0101 → 0101。"""
    text = _normalize_custom(custom)
    if not text:
        return None
    m = re.search(r"(?i)SN\s*(\d{4})", text)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\d{4}", text)
    if m:
        return text
    m = re.search(r"(\d{4})\s*$", text)
    return m.group(1) if m else text


def parse_tsv(text: str) -> list[dict[str, str]]:
    source = text.replace("\ufeff", "")
    lines = [ln for ln in source.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise LayoutParseError("文件需包含表头和至少一行数据")

    headers = [_unquote(h) for h in lines[0].split("\t")]
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        raise LayoutParseError(f"表头缺少字段: {', '.join(missing)}")

    rows: list[dict[str, str]] = []
    for i, line in enumerate(lines[1:], start=2):
        values = [_unquote(v) for v in line.split("\t")]
        if len(values) != len(headers):
            raise LayoutParseError(
                f"第 {i} 行列数不符：期望 {len(headers)}，实际 {len(values)}"
            )
        rows.append(dict(zip(headers, values)))
    return rows


def build_layout(rows: list[dict[str, str]], *, filename: str | None = None) -> dict[str, Any]:
    shots: list[dict[str, Any]] = []
    sites: list[dict[str, Any]] = []
    shot_pos: set[tuple[int, int]] = set()
    shot_custom: set[str] = set()
    site_pos: set[tuple[int, int]] = set()

    for i, row in enumerate(rows, start=2):
        level = _integer(row.get("level", ""), "level", i)
        r = _integer(row.get("reticle(struct).row", ""), "reticle(struct).row", i)
        c = _integer(row.get("reticle(struct).col", ""), "reticle(struct).col", i)
        prober = _normalize_custom(row.get("reticle(struct).prober", ""))
        custom = _normalize_custom(row.get("reticle(struct).custom", ""))
        if not custom:
            raise LayoutParseError(f"第 {i} 行：reticle(struct).custom 不能为空")

        if level == 1:
            if (r, c) in shot_pos:
                raise LayoutParseError(f"第 {i} 行：Level1 (row,col)=({r},{c}) 重复")
            if custom in shot_custom:
                raise LayoutParseError(f"第 {i} 行：Level1 custom={custom!r} 重复")
            shot_pos.add((r, c))
            shot_custom.add(custom)
            shots.append({"row": r, "col": c, "prober": prober, "custom": custom})
        elif level == 2:
            if (r, c) in site_pos:
                raise LayoutParseError(f"第 {i} 行：Level2 (row,col)=({r},{c}) 重复")
            site_pos.add((r, c))
            serial = _serial_from_custom(custom)
            sites.append(
                {
                    "row": r,
                    "col": c,
                    "prober": prober,
                    "custom": custom,
                    "serial": serial,
                }
            )
        else:
            raise LayoutParseError(f"第 {i} 行：level 只能是 1 或 2，实际为 {level}")

    if not shots:
        raise LayoutParseError("至少需要一条 Level1 Shot 记录")
    if not sites:
        raise LayoutParseError("至少需要一条 Level2 小格模板记录")

    shot_rows = [s["row"] for s in shots]
    shot_cols = [s["col"] for s in shots]
    site_rows = [s["row"] for s in sites]
    site_cols = [s["col"] for s in sites]
    site_min_row, site_max_row = min(site_rows), max(site_rows)
    site_min_col, site_max_col = min(site_cols), max(site_cols)

    occupied = {(s["row"], s["col"]) for s in sites}
    test_keys: list[dict[str, int]] = []
    for rr in range(site_min_row, site_max_row + 1):
        for cc in range(site_min_col, site_max_col + 1):
            if (rr, cc) not in occupied:
                test_keys.append({"row": rr, "col": cc})

    # custom → 图谱坐标：x=col, y=row（与前端 WaferMapView 一致）
    by_custom: dict[str, dict[str, Any]] = {}
    for s in shots:
        by_custom[str(s["custom"])] = {
            "x": int(s["col"]),
            "y": int(s["row"]),
            "row": int(s["row"]),
            "col": int(s["col"]),
            "prober": s["prober"],
            "custom": str(s["custom"]),
        }

    die_grid: list[dict[str, Any]] = []
    die_serials: list[str] = []
    site_by_pos = {(s["row"], s["col"]): s for s in sites}
    for rr in range(site_min_row, site_max_row + 1):
        for cc in range(site_min_col, site_max_col + 1):
            site = site_by_pos.get((rr, cc))
            if site is None:
                die_grid.append(
                    {
                        "row": rr - site_min_row,
                        "col": cc - site_min_col,
                        "serial": None,
                        "empty": True,
                    }
                )
            else:
                serial = site.get("serial")
                die_grid.append(
                    {
                        "row": rr - site_min_row,
                        "col": cc - site_min_col,
                        "serial": serial,
                        "empty": serial is None,
                    }
                )
                if serial:
                    die_serials.append(serial)

    layout = {
        "filename": filename or "",
        "shots": shots,
        "sites": sites,
        "test_keys": test_keys,
        "by_custom": by_custom,
        "shot_grid": {
            "min_row": min(shot_rows),
            "max_row": max(shot_rows),
            "min_col": min(shot_cols),
            "max_col": max(shot_cols),
        },
        "site_grid": {
            "min_row": site_min_row,
            "max_row": site_max_row,
            "min_col": site_min_col,
            "max_col": site_max_col,
            "rows": site_max_row - site_min_row + 1,
            "cols": site_max_col - site_min_col + 1,
        },
        "die_grid": die_grid,
        "die_serials": die_serials,
        "map_grid": {
            "min_x": min(shot_cols),
            "max_x": max(shot_cols),
            "min_y": min(shot_rows),
            "max_y": max(shot_rows),
        },
    }
    layout["summary"] = layout_summary(layout)
    return layout


def layout_summary(layout: dict[str, Any]) -> dict[str, Any]:
    sg = layout.get("shot_grid") or {}
    site = layout.get("site_grid") or {}
    return {
        "filename": layout.get("filename") or "",
        "shot_count": len(layout.get("shots") or []),
        "site_count": len(layout.get("sites") or []),
        "test_key_count": len(layout.get("test_keys") or []),
        "shot_rows": int(sg.get("max_row", 0)) - int(sg.get("min_row", 0)) + 1 if sg else 0,
        "shot_cols": int(sg.get("max_col", 0)) - int(sg.get("min_col", 0)) + 1 if sg else 0,
        "die_rows": int(site.get("rows") or 0),
        "die_cols": int(site.get("cols") or 0),
    }


def parse_layout_text(text: str, *, filename: str | None = None) -> dict[str, Any]:
    return build_layout(parse_tsv(text), filename=filename)


def lookup_shot_xy(layout: dict[str, Any], shot: str | int | None) -> tuple[int, int] | None:
    if shot is None:
        return None
    key = str(shot).strip()
    if not key:
        return None
    info = (layout.get("by_custom") or {}).get(key)
    if not info:
        return None
    return int(info["x"]), int(info["y"])
