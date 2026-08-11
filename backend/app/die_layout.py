"""Shot 内 Die 布局：3 列 × 6 行流水号（0203 位空缺）。"""

from __future__ import annotations

import re
from typing import Any

# 行优先：每行 [列1, 列2, 列3]；0203 位置为 None
DIE_SERIAL_GRID: list[list[str | None]] = [
    ["0101", "0201", "0301"],
    ["0102", "0202", "0302"],
    ["0103", None, "0303"],
    ["0104", "0204", "0304"],
    ["0105", "0205", "0305"],
    ["0106", "0206", "0306"],
]

DIE_SERIALS: list[str] = [s for row in DIE_SERIAL_GRID for s in row if s]

# 工程师库常见：""(5,5)"$$SN0202  /  "(5,5)"$$SN0202  /  SN0301
_SN_COORD_RE = re.compile(r"\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)")
_SN_SERIAL_RE = re.compile(r"SN\s*(\d{4})", re.IGNORECASE)


def parse_sn(sn: Any) -> dict[str, Any]:
    """
    解析 summaryhead.SN。
    真实库样例：
      - '\"\"(5,5)\"$$SN0202' / '\"(5,5)\"$$SN0202' → 坐标 (5,5)，流水号 0202
      - 'SN0301' → 仅流水号（Shot 可能为空）
    图谱位置以 SN 内坐标为准（与 Shot 编号无一一对应）。
    """
    raw = "" if sn is None else str(sn).strip()
    # 去掉导出/库内多余引号
    cleaned = raw.replace('""', '"').strip().strip('"').strip()

    coord_x: int | None = None
    coord_y: int | None = None
    serial: str | None = None

    m = _SN_COORD_RE.search(cleaned)
    if m:
        coord_x, coord_y = int(m.group(1)), int(m.group(2))

    m2 = _SN_SERIAL_RE.search(cleaned)
    if m2:
        serial = m2.group(1)
    else:
        m3 = re.search(r"(\d{4})\s*$", cleaned)
        if m3:
            serial = m3.group(1)

    return {
        "raw": raw,
        "coord_x": coord_x,
        "coord_y": coord_y,
        "serial": serial,
    }


def die_label(shot: str, sn_raw: str, serial: str | None) -> str:
    """展示名：有 Shot 编号时 82SN0202；无 Shot 时 SN0202。"""
    ser = serial or "----"
    shot_s = (shot or "").strip()
    # 只保留数字 Shot 号，避免把 82(7,6) 整段拼进名字
    m = re.match(r"^(\d+)", shot_s)
    if m:
        return f"{m.group(1)}SN{ser}"
    return f"SN{ser}"


def serial_grid_meta() -> list[dict[str, Any]]:
    """前端 3×6 选择器用的固定格子元数据。"""
    out: list[dict[str, Any]] = []
    for r, row in enumerate(DIE_SERIAL_GRID):
        for c, serial in enumerate(row):
            out.append(
                {
                    "row": r,
                    "col": c,
                    "serial": serial,
                    "empty": serial is None,
                }
            )
    return out
