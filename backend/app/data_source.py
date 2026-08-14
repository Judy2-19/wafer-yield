"""从 Mock 或 MySQL 读取 EAV，并按 Die（Shot + SN）透视。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import aiomysql

from .die_layout import DIE_SERIALS, die_label, parse_sn, serial_grid_meta
from .judge import apply_derived, evaluate_die, summarize
from .layout_store import get_layout, public_layout_info, require_layout
from .layout_tsv import lookup_shot_xy
from .shot_map import parse_shot, shot_to_xy
from .store import get_db_config

def _resolve_mock_path() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "mock" / "eav_rows.json",  # wafer-yield/mock
        here.parents[1] / "mock" / "eav_rows.json",  # backend/mock
        Path.cwd() / "mock" / "eav_rows.json",
        Path.cwd().parent / "mock" / "eav_rows.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


MOCK_PATH = _resolve_mock_path()

# 最近一次真库读取诊断（供 data_quality 展示）
_LAST_FETCH_STATS: dict[str, Any] = {}


def _load_mock_rows() -> list[dict[str, Any]]:
    path = _resolve_mock_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Mock 文件不存在: {path}。请确认项目含 mock/eav_rows.json，"
            f"或在「数据连接」中关闭 Mock 并填写 MySQL。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _key_str(key: Any) -> str:
    if isinstance(key, (bytes, bytearray)):
        return key.decode("utf-8", errors="ignore")
    return str(key)


def _row_get(row: dict[str, Any], *keys: str) -> Any:
    """大小写不敏感取字段；兼容 bytes 键、带表前缀的键。"""
    if not row:
        return None
    # 先精确
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    # 规范化查找
    lower_map: dict[str, Any] = {}
    for rk, rv in row.items():
        ks = _key_str(rk)
        lower_map[ks.lower()] = rv
        if "." in ks:
            lower_map[ks.split(".")[-1].lower()] = rv
    for key in keys:
        rv = lower_map.get(key.lower())
        if rv is not None:
            return rv
    return None


def _to_float(value: Any) -> float | None:
    """把库内 ItemValue（float/Decimal/str/bytes）转成 float。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        s = value.strip().strip('"').replace(",", "")
        if s == "" or s.lower() in {"null", "none", "nan"}:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_eav_row(row: dict[str, Any]) -> dict[str, Any]:
    """把查询行统一成标准字段名，避免 ItemValue/Itemvalue 识别失败。"""
    out = { _key_str(k): v for k, v in row.items() }
    # 标准别名
    mapping = {
        # 注意：这里的 ID = summaryhead.ID（不是 summarydetail.ID）
        "ID": ("ID", "Id", "id"),
        "HeadID": ("HeadID", "headid", "head_id"),  # 仅 detail 外键，值应等于 head.ID
        "Wafer": ("Wafer", "wafer"),
        "Shot": ("Shot", "shot"),
        "SN": ("SN", "sn"),
        "CreateTime": ("CreateTime", "createtime"),
        "ItemName": ("ItemName", "itemname"),
        "ItemUnit": ("ItemUnit", "Itenunit", "Itemunit", "itemunit", "Itenunit"),
        "ItemValue": ("ItemValue", "Itemvalue", "itemvalue", "Item_Value"),
        "Chnl": ("Chnl", "chnl", "Channel", "channel"),
        "WaveLength": ("WaveLength", "Wavelength", "wavelength"),
    }
    canon: dict[str, Any] = dict(out)
    for std, aliases in mapping.items():
        val = _row_get(out, *aliases)
        if val is not None:
            canon[std] = val
    return canon


# 本系统只处理 1311nm wafer 数据，其它波长一律忽略
TARGET_WAVELENGTH = "1311"


def _is_target_wavelength(wl: Any) -> bool:
    if wl is None:
        return False
    s = str(wl).strip().lower().replace("nm", "")
    # 去掉末尾 .0 / .00
    if "." in s:
        try:
            s = str(int(float(s)))
        except ValueError:
            s = s.split(".")[0]
    return s == TARGET_WAVELENGTH


def _wl_score(wl: Any) -> int:
    """保留接口；读库已过滤为仅 1311。"""
    return 2 if _is_target_wavelength(wl) else 0


def _normalize_time(value: Any) -> str:
    """统一 CreateTime，兼容 2026/8/8 15:10:00 与 2026-08-08T15:10:00。"""
    if value is None:
        return ""
    s = str(value).strip().strip('"').strip()
    if not s:
        return ""
    m = re.match(
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?",
        s,
    )
    if m:
        y, mo, d, h, mi, sec = m.groups()
        return (
            f"{int(y):04d}-{int(mo):02d}-{int(d):02d} "
            f"{int(h):02d}:{int(mi):02d}:{int(sec or 0):02d}"
        )
    return s


def _in_time_range(create_time: Any, start: str | None, end: str | None) -> bool:
    if not start and not end:
        return True
    ct = _normalize_time(create_time)
    if not ct:
        return False
    if start and ct < _normalize_time(start):
        return False
    if end and ct > _normalize_time(end):
        return False
    return True


def _id_str(value: Any) -> str | None:
    """雪花 ID 一律转字符串，避免前端 JS 精度丢失。"""
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() != "none" else None


def _die_key(shot: str, sn: str, head_pk: Any, serial: str | None = None) -> str:
    """
    Die 唯一键 = summaryhead.ID。
    关联关系：summarydetail.HeadID = summaryhead.ID
    （detail 自己也有 ID，那是明细行主键，绝不能用来当 Die）
    """
    hid = _id_str(head_pk)
    if hid:
        return f"id:{hid}"
    shot_s = (shot or "").strip() or "_"
    if serial:
        return f"{shot_s}::SN{serial}"
    sn_clean = (sn or "").strip()
    if sn_clean:
        return f"{shot_s}::{sn_clean}"
    return f"{shot_s}::unknown"


def _is_plausible_wafer_name(wafer: str) -> bool:
    """过滤导出错位行：Wafer 不应是 32(4,7) 这种 Shot 坐标形态。"""
    s = (wafer or "").strip()
    if not s:
        return False
    if re.fullmatch(r"\d+\(\-?\d+\s*,\s*\-?\d+\)", s):
        return False
    return True


def _assign_map_coordinates(dies: list[dict[str, Any]]) -> dict[str, Any]:
    """
    图谱坐标：
    - 已上传布局时：按 Level1 custom（Shot 号）映射到 (col,row)= (x,y)；
      库内 Shot/SN 嵌套坐标视为 prober，不参与画图。
    - 无布局时：兼容旧逻辑（内嵌坐标 → SN 坐标 → 编号回退）。
    返回坐标质量统计。
    """
    layout = get_layout()
    matched = 0
    unmatched: list[str] = []
    for d in dies:
        shot_key = str(d.get("shot") or "").strip()
        if layout is not None:
            xy = lookup_shot_xy(layout, shot_key) if shot_key else None
            if xy is not None:
                d["x"], d["y"] = xy
                matched += 1
            else:
                d["x"], d["y"] = None, None
                if shot_key and shot_key not in unmatched:
                    unmatched.append(shot_key)
            continue

        sx, sy = d.get("shot_x"), d.get("shot_y")
        if isinstance(sx, int) and isinstance(sy, int):
            d["x"], d["y"] = sx, sy
            continue
        sn_x, sn_y = d.get("sn_x"), d.get("sn_y")
        if isinstance(sn_x, int) and isinstance(sn_y, int):
            d["x"], d["y"] = sn_x, sn_y
            continue
        xy = shot_to_xy(d.get("shot_raw") or d.get("shot"))
        if xy is not None:
            d["x"], d["y"] = xy
        else:
            d["x"], d["y"] = None, None

    return {
        "layout_driven": layout is not None,
        "matched_dies": matched,
        "unmatched_shots": unmatched[:40],
        "unmatched_shot_count": len(unmatched),
    }


def _new_die_shell(
    *,
    dkey: str,
    wafer: str,
    shot: str,
    shot_raw: str,
    sn_raw: str,
    serial: str | None,
    shot_x: int | None,
    shot_y: int | None,
    sn_x: int | None,
    sn_y: int | None,
    create_time: str,
    head_pk: str | None,
) -> dict[str, Any]:
    return {
        "id": dkey,
        "wafer": wafer,
        "shot": shot,
        "shot_raw": shot_raw,
        "sn": sn_raw,
        "serial": serial,
        "label": die_label(shot, sn_raw, serial),
        "x": None,
        "y": None,
        "shot_x": shot_x,
        "shot_y": shot_y,
        "sn_x": sn_x,
        "sn_y": sn_y,
        "create_time": create_time,
        "head_id": head_pk,  # = summaryhead.ID
        "tests": {},
    }


def _pivot_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    按 Die 聚合测试项。
    Die 主键 = summaryhead.ID；
    明细通过 summarydetail.HeadID = summaryhead.ID 挂上；
    summarydetail.ID 是「每个参数一行」的独立主键，绝不当 Die。
    """
    by_die: dict[str, dict[str, Any]] = {}
    best: dict[str, dict[str, tuple[int, dict[str, Any]]]] = {}

    for raw in rows:
        r = _normalize_eav_row(raw if isinstance(raw, dict) else dict(raw))
        shot_raw = str(_row_get(r, "Shot", "shot") or "").strip()
        shot_info = parse_shot(shot_raw)
        shot_num = shot_info["shot"]
        # 图谱/统计用纯数字 Shot；无编号时为空（SN 误填在 Shot 栏）
        shot = str(shot_num) if shot_num is not None else ""
        name_raw = _row_get(r, "ItemName", "itemname")
        name_s = str(name_raw).strip() if name_raw is not None else ""

        wafer_raw = _row_get(r, "Wafer", "wafer")
        wafer = re.sub(r"\s*-\s*", "-", str(wafer_raw or "").strip().strip('"')).strip()
        if not _is_plausible_wafer_name(wafer):
            continue
        sn_raw = str(_row_get(r, "SN", "sn") or "").strip()
        # Die 主键 = summaryhead.ID（读库拼行后字段名 ID）
        # 兼容旧 Mock 的 HeadID（值仍是 head.ID）
        # 绝不能拿 summarydetail.ID 当 Die
        head_pk = _id_str(_row_get(r, "ID")) or _id_str(_row_get(r, "HeadID", "headid", "head_id"))
        create_time = _normalize_time(_row_get(r, "CreateTime", "createtime"))
        unit = _row_get(r, "ItemUnit", "Itenunit", "Itemunit", "itemunit")
        value = _to_float(_row_get(r, "ItemValue", "Itemvalue", "itemvalue", "Item_Value"))
        chnl = _row_get(r, "Chnl", "chnl", "Channel")
        wl = _row_get(r, "WaveLength", "Wavelength", "wavelength")

        sn_info = parse_sn(sn_raw)
        # 流水号：优先 SN 栏；否则 Shot 栏的 SN0101
        serial = sn_info["serial"] or shot_info.get("serial")
        dkey = _die_key(shot, sn_raw, head_pk, serial)
        if dkey.endswith("::unknown") and head_pk is None:
            continue

        shell_kwargs = dict(
            dkey=dkey,
            wafer=wafer,
            shot=shot,
            shot_raw=shot_raw,
            sn_raw=sn_raw,
            serial=serial,
            shot_x=shot_info.get("x"),
            shot_y=shot_info.get("y"),
            sn_x=sn_info["coord_x"],
            sn_y=sn_info["coord_y"],
            create_time=create_time,
            head_pk=head_pk,
        )

        # 占位行：仅确保 Die/Shot 出现在图谱上
        if name_s == "__HEAD__":
            if dkey not in by_die:
                by_die[dkey] = _new_die_shell(**shell_kwargs)
                best[dkey] = {}
            continue

        if not name_s:
            continue
        name = name_s

        if dkey not in by_die:
            by_die[dkey] = _new_die_shell(**shell_kwargs)
            best[dkey] = {}

        payload = {
            "value": value,
            "unit": unit,
            "chnl": str(chnl).strip() if chnl is not None and str(chnl).strip() != "" else None,
            "wavelength": wl,
        }
        score = _wl_score(wl)
        keys = [name]
        if payload["chnl"] is not None:
            keys.append(f"{name}@Chnl:{payload['chnl']}")
        for key in keys:
            prev = best[dkey].get(key)
            if prev is None or score >= prev[0]:
                best[dkey][key] = (score, payload)

    dies: list[dict[str, Any]] = []

    def _sort_key(item: tuple[str, dict[str, Any]]) -> tuple:
        d = item[1]
        shot = str(d.get("shot") or "")
        serial = str(d.get("serial") or "9999")
        try:
            shot_n = int(shot)
        except ValueError:
            shot_n = 10**9
        return (shot_n, serial)

    for dkey, die in sorted(by_die.items(), key=_sort_key):
        raw_tests = {k: v for k, (_, v) in best[dkey].items()}
        normalized = apply_derived(raw_tests)
        merged = {**raw_tests, **normalized}
        dies.append({**die, "tests": merged})
    coord_quality = _assign_map_coordinates(dies)
    for d in dies:
        d["_coord_quality"] = coord_quality
    return dies


def _aggregate_shots(dies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 Shot 汇总，供晶圆图谱点击。无 Shot 编号的 Die 不进图谱点（仍计入 stats）。"""
    by_shot: dict[str, dict[str, Any]] = {}
    for d in dies:
        shot = str(d.get("shot") or "").strip()
        if not shot:
            continue
        g = by_shot.get(shot)
        if g is None:
            g = {
                "shot": shot,
                "x": d.get("x"),
                "y": d.get("y"),
                "sn_x": d.get("sn_x"),
                "sn_y": d.get("sn_y"),
                "die_count": 0,
                "pass_count": 0,
                "fail_count": 0,
                "dies": [],
            }
            by_shot[shot] = g
        if g.get("x") is None and d.get("x") is not None:
            g["x"], g["y"] = d.get("x"), d.get("y")
        if g.get("sn_x") is None and d.get("sn_x") is not None:
            g["sn_x"], g["sn_y"] = d.get("sn_x"), d.get("sn_y")
        # 每个 die 使用各自判定结果，互不覆盖；人工未测试仍保留在图上以便恢复，
        # 但不计入 Shot/晶圆统计。
        die_pass = d.get("pass") is True
        manual_untested = d.get("manual_untested") is True
        if not manual_untested:
            g["die_count"] += 1
            if die_pass:
                g["pass_count"] += 1
            else:
                g["fail_count"] += 1
        ser = d.get("serial")
        g["dies"].append(
            {
                "id": d.get("id"),
                "shot": shot,
                "sn": d.get("sn"),
                "serial": ser,
                "label": die_label(shot, "", ser if isinstance(ser, str) else None),
                "pass": die_pass,
                "manual_untested": manual_untested,
                "create_time": d.get("create_time"),
            }
        )

    shots: list[dict[str, Any]] = []
    for shot, g in sorted(
        by_shot.items(),
        key=lambda kv: int(kv[0]) if kv[0].isdigit() else kv[0],
    ):
        # Shot Pass 当且仅当：该 Shot 下每一个已测 Die 都 Pass
        g["pass"] = g["die_count"] > 0 and g["fail_count"] == 0 and g["pass_count"] == g["die_count"]
        g["mixed"] = g["pass_count"] > 0 and g["fail_count"] > 0
        if g.get("x") is not None and g.get("y") is not None:
            g["coord_label"] = f"({g['x']},{g['y']})"
        elif g.get("sn_x") is not None and g.get("sn_y") is not None:
            g["coord_label"] = f"({g['sn_x']},{g['sn_y']})"
        else:
            g["coord_label"] = "—"
        shots.append(g)
    return shots


async def list_item_names(wafer: str | None = None) -> list[dict[str, Any]]:
    cfg = get_db_config()
    if cfg.get("use_mock", True):
        rows = _load_mock_rows()
        if wafer:
            rows = [r for r in rows if r.get("Wafer") == wafer]
        rows = [
            r
            for r in rows
            if _is_target_wavelength(_row_get(r, "WaveLength", "Wavelength", "wavelength"))
        ]
        units: dict[str, str | None] = {}
        for r in rows:
            name = str(r.get("ItemName") or "").strip()
            if not name:
                continue
            unit = r.get("Itenunit") or r.get("ItemUnit")
            if name not in units or (not units[name] and unit):
                units[name] = unit
        return [{"name": n, "unit": units[n]} for n in sorted(units.keys())]

    conn = await aiomysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        db=cfg["database"],
        charset="utf8mb4",
        autocommit=True,
    )
    wl_filter = " AND TRIM(CAST(d.WaveLength AS CHAR)) IN ('1311','1311.0','1311nm')"
    try:
        async with conn.cursor() as cur:
            if wafer:
                sql = f"""
                SELECT DISTINCT d.ItemName, d.ItemUnit
                FROM summaryhead h
                JOIN summarydetail d ON h.ID = d.HeadID
                WHERE h.Wafer = %s AND d.ItemName IS NOT NULL AND d.ItemName <> ''
                {wl_filter}
                ORDER BY d.ItemName
                """
                try:
                    await cur.execute(sql, (wafer,))
                except Exception:
                    sql = f"""
                    SELECT DISTINCT d.ItemName, d.Itenunit
                    FROM summaryhead h
                    JOIN summarydetail d ON h.ID = d.HeadID
                    WHERE h.Wafer = %s AND d.ItemName IS NOT NULL AND d.ItemName <> ''
                    {wl_filter}
                    ORDER BY d.ItemName
                    """
                    await cur.execute(sql, (wafer,))
            else:
                try:
                    await cur.execute(
                        f"""
                        SELECT DISTINCT ItemName, ItemUnit FROM summarydetail d
                        WHERE ItemName IS NOT NULL AND ItemName <> ''
                        {wl_filter}
                        ORDER BY ItemName
                        """
                    )
                except Exception:
                    await cur.execute(
                        f"""
                        SELECT DISTINCT ItemName, Itenunit FROM summarydetail d
                        WHERE ItemName IS NOT NULL AND ItemName <> ''
                        {wl_filter}
                        ORDER BY ItemName
                        """
                    )
            result = await cur.fetchall()
            seen: dict[str, str | None] = {}
            for row in result:
                name = str(row[0]).strip() if row[0] is not None else ""
                unit = row[1] if len(row) > 1 else None
                if name and name not in seen:
                    seen[name] = unit
            return [{"name": n, "unit": u} for n, u in seen.items()]
    finally:
        conn.close()


def _wafer_sort_key(name: str) -> tuple:
    """真实片号优先（UMU/DR4），导出错位的 32(4,7) 排到最后。"""
    w = (name or "").strip()
    if not _is_plausible_wafer_name(w):
        return (9, w)
    wl = w.upper()
    if wl.startswith("UMU"):
        return (0, w)
    if wl.startswith("DR"):
        return (1, w)
    return (2, w)


async def list_wafers(
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """按 CreateTime 筛选可选 Wafer（仅录入 head 时间字段）。"""
    cfg = get_db_config()
    if cfg.get("use_mock", True):
        rows = _load_mock_rows()
        buckets: dict[str, dict[str, Any]] = {}
        for r in rows:
            wafer = r.get("Wafer")
            if not wafer or not _is_plausible_wafer_name(str(wafer)):
                continue
            ct = r.get("CreateTime")
            if not _in_time_range(ct, start, end):
                continue
            b = buckets.setdefault(str(wafer), {"wafer": str(wafer), "create_times": []})
            if ct:
                b["create_times"].append(str(ct))
        out = []
        for w, b in sorted(buckets.items(), key=lambda kv: _wafer_sort_key(kv[0])):
            times = sorted(b["create_times"])
            out.append(
                {
                    "wafer": w,
                    "create_time_min": times[0] if times else None,
                    "create_time_max": times[-1] if times else None,
                }
            )
        return out

    conn = await aiomysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        db=cfg["database"],
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            sql = """
            SELECT Wafer, MIN(CreateTime) AS tmin, MAX(CreateTime) AS tmax
            FROM summaryhead
            WHERE Wafer IS NOT NULL AND Wafer <> ''
            """
            params: list[Any] = []
            if start:
                sql += " AND CreateTime >= %s"
                params.append(start)
            if end:
                sql += " AND CreateTime <= %s"
                params.append(end)
            sql += " GROUP BY Wafer ORDER BY Wafer"
            try:
                await cur.execute(sql, params)
                raw_rows = await cur.fetchall()
            except Exception:
                # 无 CreateTime 列时回退
                await cur.execute(
                    "SELECT DISTINCT Wafer FROM summaryhead WHERE Wafer IS NOT NULL ORDER BY Wafer"
                )
                raw_rows = [(r[0], None, None) for r in await cur.fetchall()]

            out = []
            for r in raw_rows:
                wafer = str(r[0]).strip() if r[0] is not None else ""
                if not _is_plausible_wafer_name(wafer):
                    continue
                out.append(
                    {
                        "wafer": wafer,
                        "create_time_min": str(r[1]) if r[1] is not None else None,
                        "create_time_max": str(r[2]) if r[2] is not None else None,
                    }
                )
            out.sort(key=lambda x: _wafer_sort_key(x["wafer"]))
            return out
    finally:
        conn.close()


async def _table_columns(cur: Any, table: str) -> set[str]:
    await cur.execute(f"SHOW COLUMNS FROM `{table}`")
    rows = await cur.fetchall()
    cols: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            name = row.get("Field") or row.get("field") or next(iter(row.values()), None)
        else:
            name = row[0]
        if name:
            cols.add(str(name))
    return cols


def _pick_col(cols: set[str], *candidates: str) -> str | None:
    lower_map = {c.lower(): c for c in cols}
    for name in candidates:
        if name in cols:
            return name
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


async def fetch_eav_rows(
    wafer: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """
    读库流程（工程师口径）：
    1) summaryhead 按 Wafer 取行；每行的 ID = 一颗 Die
    2) summarydetail 用 HeadID = summaryhead.ID 拉明细
       （detail.ID 是明细行自己的主键，不用来关联）
    3) 实测只保留 WaveLength=1311
    """
    cfg = get_db_config()
    if cfg.get("use_mock", True):
        rows = _load_mock_rows()
        return [
            r
            for r in rows
            if r.get("Wafer") == wafer
            and _in_time_range(r.get("CreateTime"), start, end)
            and _is_target_wavelength(_row_get(r, "WaveLength", "Wavelength", "wavelength"))
        ]

    conn = await aiomysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        db=cfg["database"],
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            head_cols = await _table_columns(cur, "summaryhead")
            detail_cols = await _table_columns(cur, "summarydetail")

            # head 只有 ID；detail 有 ID + HeadID，关联键是 detail.HeadID → head.ID
            id_col = _pick_col(head_cols, "ID", "Id", "id")
            wafer_col = _pick_col(head_cols, "Wafer", "wafer")
            shot_col = _pick_col(head_cols, "Shot", "shot")
            sn_col = _pick_col(head_cols, "SN", "Sn", "sn")
            head_ct = _pick_col(head_cols, "CreateTime", "createtime")
            detail_head_fk = _pick_col(detail_cols, "HeadID", "HeadId", "headid")
            item_col = _pick_col(detail_cols, "ItemName", "itemname")
            unit_col = _pick_col(detail_cols, "ItemUnit", "Itenunit", "Itemunit", "itemunit")
            value_col = _pick_col(detail_cols, "ItemValue", "Itemvalue", "itemvalue")
            chnl_col = _pick_col(detail_cols, "Chnl", "Channel", "chnl")
            wl_col = _pick_col(detail_cols, "WaveLength", "Wavelength", "wavelength")

            if not id_col or not wafer_col or not shot_col or not detail_head_fk or not item_col or not value_col:
                raise RuntimeError(
                    "summaryhead/summarydetail 缺少必要列 "
                    f"(head={sorted(head_cols)}, detail={sorted(detail_cols)})"
                )

            # ---------- 1) summaryhead：按 Wafer 取所有 Die 的 ID ----------
            sn_expr = f"h.`{sn_col}` AS SN" if sn_col else "NULL AS SN"
            ct_expr = f"h.`{head_ct}` AS CreateTime" if head_ct else "NULL AS CreateTime"
            head_sql = f"""
                SELECT
                  CAST(h.`{id_col}` AS CHAR) AS ID,
                  h.`{wafer_col}` AS Wafer,
                  h.`{shot_col}` AS Shot,
                  {sn_expr},
                  {ct_expr}
                FROM summaryhead h
                WHERE h.`{wafer_col}` = %s
            """
            head_params: list[Any] = [wafer]
            if head_ct and start:
                head_sql += f" AND h.`{head_ct}` >= %s"
                head_params.append(start)
            if head_ct and end:
                head_sql += f" AND h.`{head_ct}` <= %s"
                head_params.append(end)

            await cur.execute(head_sql, head_params)
            heads = [_normalize_eav_row(dict(r)) for r in await cur.fetchall()]
            if not heads:
                _LAST_FETCH_STATS.clear()
                _LAST_FETCH_STATS.update(
                    {"wafer": wafer, "head_rows": 0, "detail_rows": 0, "eav_1311": 0}
                )
                return []

            head_ids = [_id_str(_row_get(h, "ID")) for h in heads]
            head_ids = [i for i in head_ids if i]
            if not head_ids:
                return []

            head_by_id = {_id_str(_row_get(h, "ID")): h for h in heads}

            # ---------- 2) summarydetail：WHERE HeadID IN (head.ID…) ----------
            # 不 SELECT detail.ID，避免和 head.ID 搞混
            unit_expr = f"d.`{unit_col}` AS ItemUnit" if unit_col else "NULL AS ItemUnit"
            chnl_expr = f"d.`{chnl_col}` AS Chnl" if chnl_col else "NULL AS Chnl"
            wl_expr = f"d.`{wl_col}` AS WaveLength" if wl_col else "NULL AS WaveLength"

            detail_rows: list[dict[str, Any]] = []
            batch_size = 400
            for i in range(0, len(head_ids), batch_size):
                batch_str = head_ids[i : i + batch_size]
                batch_params: list[Any] = [
                    int(hid) if hid.isdigit() else hid for hid in batch_str
                ]
                placeholders = ",".join(["%s"] * len(batch_params))
                detail_sql = f"""
                    SELECT
                      CAST(d.`{detail_head_fk}` AS CHAR) AS HeadID,
                      d.`{item_col}` AS ItemName,
                      {unit_expr},
                      d.`{value_col}` AS ItemValue,
                      {chnl_expr},
                      {wl_expr}
                    FROM summarydetail d
                    WHERE d.`{detail_head_fk}` IN ({placeholders})
                """
                await cur.execute(detail_sql, batch_params)
                detail_rows.extend(_normalize_eav_row(dict(r)) for r in await cur.fetchall())

            # 原生 IN 0 行时，用 CAST 字符串再试（兼容字符型/空格）
            if not detail_rows and head_ids:
                for i in range(0, len(head_ids), batch_size):
                    batch_str = head_ids[i : i + batch_size]
                    placeholders = ",".join(["%s"] * len(batch_str))
                    detail_sql = f"""
                        SELECT
                          TRIM(CAST(d.`{detail_head_fk}` AS CHAR)) AS HeadID,
                          d.`{item_col}` AS ItemName,
                          {unit_expr},
                          d.`{value_col}` AS ItemValue,
                          {chnl_expr},
                          {wl_expr}
                        FROM summarydetail d
                        WHERE TRIM(CAST(d.`{detail_head_fk}` AS CHAR)) IN ({placeholders})
                    """
                    await cur.execute(detail_sql, batch_str)
                    detail_rows.extend(_normalize_eav_row(dict(r)) for r in await cur.fetchall())

            # ---------- 3) 用 detail.HeadID = head.ID 拼回；只保留 1311 ----------
            eav: list[dict[str, Any]] = []
            heads_with_detail: set[str] = set()
            for d in detail_rows:
                # detail.HeadID 的值就是 head.ID
                hid = _id_str(_row_get(d, "HeadID"))
                if not hid or hid not in head_by_id:
                    continue
                if not _is_target_wavelength(_row_get(d, "WaveLength")):
                    continue
                heads_with_detail.add(hid)
                h = head_by_id[hid]
                eav.append(
                    {
                        "ID": hid,  # = summaryhead.ID（Die 主键）
                        "Wafer": _row_get(h, "Wafer"),
                        "Shot": _row_get(h, "Shot"),
                        "SN": _row_get(h, "SN"),
                        "CreateTime": _row_get(h, "CreateTime"),
                        "ItemName": _row_get(d, "ItemName"),
                        "ItemUnit": _row_get(d, "ItemUnit"),
                        "ItemValue": _row_get(d, "ItemValue"),
                        "Chnl": _row_get(d, "Chnl"),
                        "WaveLength": _row_get(d, "WaveLength"),
                    }
                )

            # 无 1311 明细的 Die 也占位，保证 Shot（含 80/90 段）能出现
            for hid, h in head_by_id.items():
                if not hid or hid in heads_with_detail:
                    continue
                eav.append(
                    {
                        "ID": hid,
                        "Wafer": _row_get(h, "Wafer"),
                        "Shot": _row_get(h, "Shot"),
                        "SN": _row_get(h, "SN"),
                        "CreateTime": _row_get(h, "CreateTime"),
                        "ItemName": "__HEAD__",
                        "ItemUnit": None,
                        "ItemValue": None,
                        "Chnl": None,
                        "WaveLength": TARGET_WAVELENGTH,
                    }
                )

            valued = sum(
                1
                for r in eav
                if r.get("ItemName") != "__HEAD__"
                and _to_float(_row_get(r, "ItemValue")) is not None
            )
            _LAST_FETCH_STATS.clear()
            _LAST_FETCH_STATS.update(
                {
                    "wafer": wafer,
                    "join": "summarydetail.HeadID = summaryhead.ID",
                    "head_rows": len(heads),
                    "detail_rows_raw": len(detail_rows),
                    "heads_with_1311": len(heads_with_detail),
                    "eav_1311": sum(1 for r in eav if r.get("ItemName") != "__HEAD__"),
                    "valued_itemvalue": valued,
                    "sample_head_id": head_ids[:3],
                }
            )
            return eav
    finally:
        conn.close()


async def get_dies(
    wafer: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    rows = await fetch_eav_rows(wafer, start=start, end=end)
    return _pivot_rows(rows)


async def judge_wafer(
    wafer: str,
    specs: list[dict[str, Any]],
    start: str | None = None,
    end: str | None = None,
    manual_untested_die_ids: set[str] | None = None,
) -> dict[str, Any]:
    layout = require_layout()
    dies_raw = await get_dies(wafer, start=start, end=end)
    judged: list[dict[str, Any]] = []
    coord_quality: dict[str, Any] = {"layout_driven": True}
    for die in dies_raw:
        if "_coord_quality" in die:
            coord_quality = die.pop("_coord_quality", coord_quality)
        result = evaluate_die(die["tests"], specs)
        judged.append(
            {
                **die,
                **result,
                "manual_untested": str(die.get("id")) in (manual_untested_die_ids or set()),
            }
        )
    stats = summarize(judged, specs)
    shots = _aggregate_shots(judged)
    map_grid = dict(layout.get("map_grid") or {})

    # 诊断：有多少 Die 读到了非空 ItemValue（便于排查 Note 空白 / HeadID 未联通）
    valued = 0
    sample_keys: list[str] = []
    head_ids_sample: list[str] = []
    shots_high: list[str] = []
    for d in judged:
        hid = d.get("head_id")
        if hid and len(head_ids_sample) < 6:
            head_ids_sample.append(str(hid))
        shot = str(d.get("shot") or "")
        if shot.isdigit() and int(shot) >= 80 and shot not in shots_high:
            shots_high.append(shot)
        for k, t in (d.get("tests") or {}).items():
            if isinstance(t, dict) and t.get("value") is not None:
                valued += 1
                if len(sample_keys) < 8:
                    sample_keys.append(f"ID:{hid}|{k}={t.get('value')}")
    return {
        "wafer": wafer,
        "dies": judged,
        "shots": shots,
        "stats": stats,
        "die_grid": layout.get("die_grid") or serial_grid_meta(),
        "die_serials": layout.get("die_serials") or DIE_SERIALS,
        "map_grid": map_grid,
        "layout": public_layout_info(layout),
        "data_quality": {
            "wavelength": TARGET_WAVELENGTH,
            "die_count": len(judged),
            "shot_count": len(shots),
            "valued_test_count": valued,
            "sample": sample_keys,
            "head_id_sample": head_ids_sample,
            "shots_ge_80": sorted(shots_high, key=lambda s: int(s)),
            "fetch": dict(_LAST_FETCH_STATS),
            "coord": coord_quality,
            "schema_note": (
                "Die=summaryhead.ID; 参数行=summarydetail.ID; "
                "关联 summarydetail.HeadID=summaryhead.ID; 只读 1311; "
                "图谱坐标由上传的 Level1 custom→(col,row) 决定"
            ),
        },
    }


async def test_mysql_connection(cfg: dict[str, Any]) -> dict[str, Any]:
    if cfg.get("use_mock"):
        _load_mock_rows()
        return {"ok": True, "message": "当前为 Mock 模式，本地样例数据可读"}

    host = cfg["host"]
    port = int(cfg["port"])
    user = cfg["user"]
    password = cfg["password"]
    database = cfg["database"]
    common = dict(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        connect_timeout=5,
        autocommit=True,
    )

    try:
        conn = await aiomysql.connect(**common, db=database)
    except Exception as exc:
        text = str(exc)
        if "1049" in text or "Unknown database" in text:
            try:
                probe = await aiomysql.connect(**common)
                try:
                    async with probe.cursor() as cur:
                        await cur.execute("SHOW DATABASES")
                        dbs = [r[0] for r in await cur.fetchall()]
                finally:
                    probe.close()
                listed = ", ".join(dbs) if dbs else "(无)"
                return {
                    "ok": False,
                    "message": (
                        f"账号密码正确，但服务器上不存在库 `{database}`。"
                        f"当前已有库：{listed}。"
                        f"请在 MySQL 执行 CREATE DATABASE `{database}`，"
                        f"或双击 wafer-yield/mysql/创建数据库.bat。"
                    ),
                }
            except Exception:
                return {
                    "ok": False,
                    "message": (
                        f"账号密码正确，但库 `{database}` 不存在。"
                        f"请先创建该数据库后再测连。"
                    ),
                }
        return {"ok": False, "message": text}

    try:
        async with conn.cursor() as cur:
            try:
                await cur.execute("SELECT COUNT(*) FROM summaryhead")
                (count,) = await cur.fetchone()
            except Exception as exc:
                return {
                    "ok": False,
                    "message": (
                        f"已连上库 `{database}`，但缺少表 summaryhead："
                        f"{exc}。请核对 summaryhead/summarydetail 表结构。"
                    ),
                }
        return {"ok": True, "message": f"连接成功，summaryhead 约 {count} 行"}
    finally:
        conn.close()


def collect_param_names(dies: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for d in dies:
        names.update(d.get("tests", {}).keys())
    return sorted(names)
