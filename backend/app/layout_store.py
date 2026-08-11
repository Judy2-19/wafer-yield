"""当前 Shot 布局会话（上传后驻留内存，并落盘便于重启恢复）。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .layout_tsv import layout_summary, parse_layout_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LAYOUT_PATH = DATA_DIR / "current_layout.json"

_current: dict[str, Any] | None = None


def _load_from_disk() -> dict[str, Any] | None:
    if not LAYOUT_PATH.exists():
        return None
    try:
        raw = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("shots") and raw.get("sites"):
            return raw
    except Exception:
        return None
    return None


def get_layout() -> dict[str, Any] | None:
    global _current
    if _current is not None:
        return _current
    _current = _load_from_disk()
    return _current


def require_layout() -> dict[str, Any]:
    layout = get_layout()
    if layout is None:
        raise RuntimeError("尚未上传 Shot 布局文件。请先上传类似 SF_DR8.txt 的 Level1/2 TSV。")
    return layout


def set_layout_from_text(text: str, *, filename: str | None = None) -> dict[str, Any]:
    global _current
    layout = parse_layout_text(text, filename=filename)
    layout_id = uuid.uuid4().hex[:12]
    layout["layout_id"] = layout_id
    layout["summary"] = {
        **layout_summary(layout),
        "layout_id": layout_id,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 落盘时去掉过大无关字段亦可；此处完整保存便于重启恢复
    LAYOUT_PATH.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    _current = layout
    return layout


def clear_layout() -> None:
    global _current
    _current = None
    if LAYOUT_PATH.exists():
        LAYOUT_PATH.unlink()


def public_layout_info(layout: dict[str, Any] | None = None) -> dict[str, Any] | None:
    lay = layout if layout is not None else get_layout()
    if lay is None:
        return None
    summary = lay.get("summary") or layout_summary(lay)
    return {
        "layout_id": lay.get("layout_id") or summary.get("layout_id"),
        "filename": lay.get("filename") or "",
        "summary": summary,
        "map_grid": lay.get("map_grid"),
        "die_grid": lay.get("die_grid"),
        "die_serials": lay.get("die_serials"),
        "test_keys": lay.get("test_keys"),
    }
