"""Shot 解析与图谱坐标回退。

真实库 summaryhead.Shot（见 新head_utf8.csv）：
  - '82(7,6)' / '85(7,3)' / '51(5,5)' → Shot编号 + 图谱坐标 (x,y)
  - 'SN0101' → Shot 栏误填流水号（无 Shot 编号）
  - '56' → 仅编号

图谱坐标优先级（在 data_source 中）：
  1) Shot 字段内的 (x,y)
  2) SN 字段内的 (x,y)
  3) 按 Shot编号=列×10+行 回退
"""

from __future__ import annotations

import re
from typing import Any

COLS = 10
ROWS = 6
GRID_MIN_X = 1
GRID_MAX_X = COLS
GRID_MIN_Y = 1
GRID_MAX_Y = ROWS

ROW_SHOT_COUNTS: dict[int, int] = {
    1: 5,
    2: 7,
    3: 7,
    4: 7,
    5: 5,
    6: 3,
}

# 82(7,6) / Shot82(7,6)
_SHOT_WITH_XY = re.compile(
    r"^\s*(?:Shot)?\s*(\d+)\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*$",
    re.IGNORECASE,
)
# Shot 栏只有流水号
_SHOT_SN_ONLY = re.compile(r"^\s*SN\s*(\d{4})\s*$", re.IGNORECASE)
# 纯数字
_SHOT_NUM_ONLY = re.compile(r"^\s*(?:Shot)?\s*(\d+)(?:\.0+)?\s*$", re.IGNORECASE)


def cols_for_row(row: int) -> list[int]:
    n = ROW_SHOT_COUNTS.get(row)
    if not n:
        return []
    start = (COLS - n) // 2 + 1
    return list(range(start, start + n))


def _build_valid_positions() -> dict[int, tuple[int, int]]:
    mapping: dict[int, tuple[int, int]] = {}
    for row in range(1, ROWS + 1):
        for col in cols_for_row(row):
            shot = col * 10 + row
            mapping[shot] = (col, row)
    return mapping


SHOT_TO_XY: dict[int, tuple[int, int]] = _build_valid_positions()
XY_TO_SHOT: dict[tuple[int, int], int] = {xy: s for s, xy in SHOT_TO_XY.items()}
VALID_XY: set[tuple[int, int]] = set(SHOT_TO_XY.values())


def parse_shot(shot: Any) -> dict[str, Any]:
    """
    解析 summaryhead.Shot。
    返回: shot(int|None), x, y, serial(从 Shot 栏拆出的流水号), raw
    """
    if shot is None:
        return {"shot": None, "x": None, "y": None, "serial": None, "raw": ""}
    if isinstance(shot, bool):
        return {"shot": None, "x": None, "y": None, "serial": None, "raw": ""}
    if isinstance(shot, int):
        n = shot if shot > 0 else None
        return {"shot": n, "x": None, "y": None, "serial": None, "raw": str(shot)}
    if isinstance(shot, float):
        if shot != shot or shot <= 0:
            return {"shot": None, "x": None, "y": None, "serial": None, "raw": str(shot)}
        return {"shot": int(shot), "x": None, "y": None, "serial": None, "raw": str(shot)}

    raw = str(shot).strip().strip('"').strip()
    if not raw:
        return {"shot": None, "x": None, "y": None, "serial": None, "raw": ""}

    m = _SHOT_WITH_XY.match(raw)
    if m:
        return {
            "shot": int(m.group(1)),
            "x": int(m.group(2)),
            "y": int(m.group(3)),
            "serial": None,
            "raw": raw,
        }

    m = _SHOT_SN_ONLY.match(raw)
    if m:
        return {
            "shot": None,
            "x": None,
            "y": None,
            "serial": m.group(1),
            "raw": raw,
        }

    m = _SHOT_NUM_ONLY.match(raw)
    if m:
        return {
            "shot": int(m.group(1)),
            "x": None,
            "y": None,
            "serial": None,
            "raw": raw,
        }

    # 兜底：取第一段数字当 Shot 号（避免把 SN0101 误判成 101：上面已拦截）
    m = re.search(r"(\d+)", raw)
    if m and not re.search(r"SN", raw, re.I):
        return {
            "shot": int(m.group(1)),
            "x": None,
            "y": None,
            "serial": None,
            "raw": raw,
        }
    return {"shot": None, "x": None, "y": None, "serial": None, "raw": raw}


def normalize_shot_number(shot: int | str | None) -> int | None:
    """提取 Shot 编号；'SN0101' 返回 None（不是 Shot 号）。"""
    return parse_shot(shot)["shot"]


def shot_to_col_row(shot: int | str | None) -> tuple[int, int] | None:
    """
    由 Shot 得到图谱 (列, 行)。
    优先用字段内嵌坐标 82(7,6)→(7,6)；否则按编号回退。
    """
    info = parse_shot(shot)
    if isinstance(info["x"], int) and isinstance(info["y"], int):
        return info["x"], info["y"]

    n = info["shot"]
    if n is None:
        return None
    if n in SHOT_TO_XY:
        return SHOT_TO_XY[n]
    col, row = divmod(n, 10)
    if col == 0:
        return None
    if 1 <= col <= 12 and 1 <= row <= 9:
        return col, row
    return None


def shot_to_xy(shot: int | str | None) -> tuple[int, int] | None:
    return shot_to_col_row(shot)


def xy_to_shot(x: int, y: int) -> int | None:
    return XY_TO_SHOT.get((x, y))


def all_shots() -> list[int]:
    return sorted(SHOT_TO_XY.keys())


def grid_meta() -> dict[str, int | list[int]]:
    return {
        "min_x": GRID_MIN_X,
        "max_x": GRID_MAX_X,
        "min_y": GRID_MIN_Y,
        "max_y": GRID_MAX_Y,
        "cols": COLS,
        "rows": ROWS,
        "row_counts": [ROW_SHOT_COUNTS[r] for r in range(1, ROWS + 1)],
        "valid_shot_count": len(SHOT_TO_XY),
    }
