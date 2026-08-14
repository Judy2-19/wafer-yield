"""当前 Shot 布局会话（上传后驻留内存，并落盘便于重启恢复）。"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .layout_tsv import layout_summary, parse_layout_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LAYOUT_PATH = DATA_DIR / "current_layout.json"
TEMPLATE_DIR = DATA_DIR / "layout_templates"
CURRENT_ID_PATH = DATA_DIR / "current_layout_id.txt"

_current: dict[str, Any] | None = None


def layout_id_for_text(text: str, filename: str | None = None) -> str:
    """有文件名时按文件名稳定编号；缺少文件名时退回按内容编号。"""
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    normalized_name = Path(filename).name.strip().casefold() if filename else ""
    identity = f"filename:{normalized_name}" if normalized_name else f"content:{normalized}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def _template_with_filename(filename: str | None) -> dict[str, Any] | None:
    normalized_name = Path(filename).name.strip().casefold() if filename else ""
    if not normalized_name or not TEMPLATE_DIR.exists():
        return None
    for path in TEMPLATE_DIR.glob("*.json"):
        layout = _read_json(path)
        stored_name = Path(str(layout.get("filename") or "")).name.strip().casefold() if layout else ""
        if layout is not None and stored_name == normalized_name:
            return layout
    return None


def _load_from_disk() -> dict[str, Any] | None:
    _migrate_legacy_layout()
    layout_id = _read_current_id()
    if layout_id:
        layout = _read_template(layout_id)
        if layout is not None:
            return layout
    templates = list(TEMPLATE_DIR.glob("*.json")) if TEMPLATE_DIR.exists() else []
    if templates:
        layout = _read_json(templates[0])
        if layout is not None:
            _set_current(layout)
            return layout
    return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("shots") and raw.get("sites"):
            return raw
    except Exception:
        return None
    return None


def _template_path(layout_id: str) -> Path:
    safe_id = "".join(ch for ch in str(layout_id) if ch.isalnum() or ch in {"-", "_"})
    if not safe_id or safe_id != str(layout_id):
        raise ValueError("无效的布局模板编号")
    return TEMPLATE_DIR / f"{safe_id}.json"


def _read_template(layout_id: str) -> dict[str, Any] | None:
    try:
        return _read_json(_template_path(layout_id))
    except ValueError:
        return None


def _read_current_id() -> str | None:
    if not CURRENT_ID_PATH.exists():
        return None
    try:
        return CURRENT_ID_PATH.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def _default_template_name(filename: str | None) -> str:
    name = Path(filename or "Shot 布局").stem.strip()
    return name or "Shot 布局"


def _prepare_layout(layout: dict[str, Any], *, layout_id: str, name: str | None = None) -> dict[str, Any]:
    layout["layout_id"] = layout_id
    layout["name"] = (name or layout.get("name") or _default_template_name(layout.get("filename"))).strip()
    layout["summary"] = {
        **(layout.get("summary") or layout_summary(layout)),
        "layout_id": layout_id,
    }
    return layout


def _write_template(layout: dict[str, Any]) -> None:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    _template_path(str(layout["layout_id"])).write_text(
        json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _set_current(layout: dict[str, Any]) -> None:
    global _current
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_ID_PATH.write_text(str(layout["layout_id"]), encoding="utf-8")
    # 保留旧路径，便于旧版本程序和人工备份继续读取。
    LAYOUT_PATH.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    _current = layout


def _migrate_legacy_layout() -> None:
    if TEMPLATE_DIR.exists() and any(TEMPLATE_DIR.glob("*.json")):
        return
    legacy = _read_json(LAYOUT_PATH) if LAYOUT_PATH.exists() else None
    if legacy is None:
        return
    layout_id = str(legacy.get("layout_id") or hashlib.sha256(
        json.dumps(legacy, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12])
    _prepare_layout(legacy, layout_id=layout_id)
    _write_template(legacy)
    _set_current(legacy)


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
    layout = parse_layout_text(text, filename=filename)
    existing = _template_with_filename(filename)
    layout_id = str(existing.get("layout_id")) if existing else layout_id_for_text(text, filename)
    existing = existing or _read_template(layout_id)
    existing_name = existing.get("name") if existing else None
    _prepare_layout(layout, layout_id=layout_id, name=existing_name)
    _write_template(layout)
    _set_current(layout)
    return layout


def list_layout_templates() -> list[dict[str, Any]]:
    _migrate_legacy_layout()
    current_id = _read_current_id()
    items: list[dict[str, Any]] = []
    for path in sorted(TEMPLATE_DIR.glob("*.json")) if TEMPLATE_DIR.exists() else []:
        layout = _read_json(path)
        if layout is None:
            continue
        layout_id = str(layout.get("layout_id") or path.stem)
        items.append(
            {
                "layout_id": layout_id,
                "name": layout.get("name") or _default_template_name(layout.get("filename")),
                "filename": layout.get("filename") or "",
                "summary": layout.get("summary") or layout_summary(layout),
                "current": layout_id == current_id,
            }
        )
    return items


def select_layout_template(layout_id: str) -> dict[str, Any]:
    layout = _read_template(layout_id)
    if layout is None:
        raise KeyError("布局模板不存在")
    _set_current(layout)
    return layout


def rename_layout_template(layout_id: str, name: str) -> dict[str, Any]:
    layout = _read_template(layout_id)
    if layout is None:
        raise KeyError("布局模板不存在")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("布局模板名称不能为空")
    layout["name"] = clean_name
    _write_template(layout)
    if _read_current_id() == layout_id:
        _set_current(layout)
    return layout


def delete_layout_template(layout_id: str) -> dict[str, Any] | None:
    global _current
    path = _template_path(layout_id)
    if not path.exists():
        raise KeyError("布局模板不存在")
    was_current = _read_current_id() == layout_id
    path.unlink()
    if was_current:
        _current = None
        # 先清除当前指针和旧版兼容副本，避免空模板库被旧文件立即迁移回来。
        if CURRENT_ID_PATH.exists():
            CURRENT_ID_PATH.unlink()
        if LAYOUT_PATH.exists():
            LAYOUT_PATH.unlink()
    remaining = list_layout_templates()
    if was_current:
        if remaining:
            return select_layout_template(str(remaining[0]["layout_id"]))
    return get_layout()


def clear_layout() -> None:
    global _current
    _current = None
    if LAYOUT_PATH.exists():
        LAYOUT_PATH.unlink()
    if CURRENT_ID_PATH.exists():
        CURRENT_ID_PATH.unlink()


def public_layout_info(layout: dict[str, Any] | None = None) -> dict[str, Any] | None:
    lay = layout if layout is not None else get_layout()
    if lay is None:
        return None
    summary = lay.get("summary") or layout_summary(lay)
    return {
        "layout_id": lay.get("layout_id") or summary.get("layout_id"),
        "name": lay.get("name") or _default_template_name(lay.get("filename")),
        "filename": lay.get("filename") or "",
        "summary": summary,
        "map_grid": lay.get("map_grid"),
        "shots": lay.get("shots"),
        "die_grid": lay.get("die_grid"),
        "die_serials": lay.get("die_serials"),
        "test_keys": lay.get("test_keys"),
    }
