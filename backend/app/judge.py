"""多参数 Min/Max 判定与详情行构建。"""

from __future__ import annotations

import math
import re
from typing import Any

from .specs import (
    COND_VR_MPD_1,
    COND_VR_MPD_4,
    DETAIL_ROWS,
    ITEM_ALIASES,
    LEGACY_MPD_KEYS,
    MPD_DARK_1V_ITEMS,
    MPD_DARK_4V_ITEMS,
)

# 库内暗电流相关 ItemName：MPD-2B--1 / MPDin--2 / MPDin2--1
_MPD_ITEM_RE = re.compile(r"^(MPD-\d+[AB]|MPDin2?|MPDin)--?\d+$", re.IGNORECASE)


def in_spec(value: float | None, lsl: float | None, usl: float | None) -> bool | None:
    if value is None:
        return None
    if lsl is not None and value < lsl:
        return False
    if usl is not None and value > usl:
        return False
    return True


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:g}"


def _pick(tests: dict[str, dict[str, Any]], *names: str) -> dict[str, Any] | None:
    for name in names:
        if name in tests and tests[name].get("value") is not None:
            return tests[name]
        # 忽略大小写匹配
        lower = name.lower()
        for key, item in tests.items():
            base = key.split("@Chnl:")[0]
            if base.lower() == lower and item.get("value") is not None:
                return item
    return None


def _num(tests: dict[str, dict[str, Any]], *names: str, chnl: str | int | None = None) -> float | None:
    if chnl is not None:
        ch = str(chnl).strip()
        for name in names:
            for key in (f"{name}@Chnl:{ch}", f"{name}|Chnl:{ch}", name):
                item = tests.get(key)
                if item is not None and item.get("value") is not None:
                    return float(item["value"])
            # 大小写宽松
            lower = name.lower()
            for key, item in tests.items():
                if item.get("value") is None:
                    continue
                if "@Chnl:" in key:
                    base, _, c = key.partition("@Chnl:")
                    if base.lower() == lower and c == ch:
                        return float(item["value"])
    item = _pick(tests, *names)
    return float(item["value"]) if item else None


def _safe_log10_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    if a <= 0 or b <= 0:
        return None
    return 10.0 * math.log10(a / b)


def normalize_tests(tests: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """将库内 ItemName 规范化为详情 key，并计算派生项。"""
    out: dict[str, dict[str, Any]] = {}

    # 1) On Chip Loss + EC_EC Loss = OnChipLoss + EC-EC（缺一项也写入，供 Note 显示）
    on_chip = _num(tests, "OnChipLoss", "On Chip Loss")
    ec_ec = _num(tests, "EC-EC", "EC_EC", "EC_EC Loss")
    if on_chip is not None or ec_ec is not None:
        total = (on_chip + ec_ec) if on_chip is not None and ec_ec is not None else None
        out["On Chip Loss + EC_EC Loss"] = {
            "value": total,
            "unit": "dB",
            "parts": {
                "OnChipLoss": on_chip,
                "EC-EC": ec_ec,
                "sum": total,
            },
        }

    # 2) MZM Loss：OnChipLoss_2 与 OnChipLoss_3 都要合格
    mzm2 = _num(tests, "OnChipLoss_2")
    mzm3 = _num(tests, "OnChipLoss_3")
    if mzm2 is not None or mzm3 is not None:
        vals = [v for v in (mzm2, mzm3) if v is not None]
        out["MZM Loss"] = {
            "value": max(vals) if vals else None,
            "unit": "dB",
            "parts": {"OnChipLoss_2": mzm2, "OnChipLoss_3": mzm3},
            "multi_all": True,
        }

    # 3) OutMPD Imbalance = 10*log10(OpticCurrMpdA/OpticCurrMpdB)
    out_a = _num(tests, "OpticCurrMpdA", "OpticCurrMPDA", "OpticCurrMpd_A")
    out_b = _num(tests, "OpticCurrMpdB", "OpticCurrMPDB", "OpticCurrMpd_B")
    out_val = _safe_log10_ratio(out_a, out_b)
    if out_a is not None or out_b is not None or out_val is not None:
        out["OutMPD Imbalance"] = {
            "value": out_val,
            "unit": "dB",
            "parts": {"OpticCurrMpdA": out_a, "OpticCurrMpdB": out_b},
        }

    # 4) InMPD Imbalance
    # 10*log10(OpitcCurrMpdIn@5 / OpitcCurrMpdIn@1) - (InputPower@5 - InputPower@1)
    in5 = _num(
        tests,
        "OpitcCurrMpdIn",
        "OpticCurrMpdIn",
        "OpitcCurrMpdIn(Chnl:5)",
        chnl=5,
    )
    in1 = _num(
        tests,
        "OpitcCurrMpdIn",
        "OpticCurrMpdIn",
        "OpitcCurrMpdIn(Chnl:1)",
        chnl=1,
    )
    pin5 = _num(tests, "InputPower", "InputPower(Chnl:5)", "InputPower(Chni:5)", chnl=5)
    pin1 = _num(tests, "InputPower", "InputPower(Chnl:1)", "InputPower(Chni:1)", chnl=1)
    ratio = _safe_log10_ratio(in5, in1)
    in_val = None
    if ratio is not None and pin5 is not None and pin1 is not None:
        in_val = ratio - (pin5 - pin1)
    if any(v is not None for v in (in5, in1, pin5, pin1, in_val)):
        out["InMPD Imbalance"] = {
            "value": in_val,
            "unit": "dB",
            "parts": {
                "OpitcCurrMpdIn@5": in5,
                "OpitcCurrMpdIn@1": in1,
                "InputPower@5": pin5,
                "InputPower@1": pin1,
            },
        }

    # 5) MPD Dark Current：固定子项 + 库里实际出现的 MPD*/MPDin* 动态并入
    def _mpd_names_from_tests() -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for raw_key, item in tests.items():
            if item.get("value") is None:
                continue
            base = raw_key.split("@Chnl:")[0]
            if base in seen:
                continue
            # 只收库内原始项名，排除派生 key「MPD Dark Current」
            if _MPD_ITEM_RE.match(base):
                seen.add(base)
                names.append(base)
        return names

    def _collect_mpd_items(names: list[str]) -> list[dict[str, Any]]:
        children = []
        for name in names:
            v = _num(tests, name)
            children.append({"item": name, "name": name, "value": v, "unit": "nA"})
        return children

    extra_mpd = _mpd_names_from_tests()
    names_1v = list(MPD_DARK_1V_ITEMS)
    names_4v = list(MPD_DARK_4V_ITEMS)
    names_other: list[str] = []
    known = set(names_1v) | set(names_4v)
    for n in extra_mpd:
        if n in known:
            continue
        if n.endswith("--1"):
            names_1v.append(n)
        elif n.endswith("--4"):
            names_4v.append(n)
        else:
            # 如 MPDin--2：不在标准 1V/4V 列表，仍要展示实测
            names_other.append(n)
        known.add(n)

    items_1v = _collect_mpd_items(names_1v)
    items_4v = _collect_mpd_items(names_4v)
    items_other = _collect_mpd_items(names_other)
    present = [
        c["value"]
        for c in items_1v + items_4v + items_other
        if c["value"] is not None
    ]
    groups: list[dict[str, Any]] = [
        {
            "key": "1.0V",
            "item": "1.0V",
            "name": "1.0V",
            "condition": COND_VR_MPD_1,
            "unit": "nA",
            "children": items_1v,
        },
        {
            "key": "4.0V",
            "item": "4.0V",
            "name": "4.0V",
            "condition": COND_VR_MPD_4,
            "unit": "nA",
            "children": items_4v,
        },
    ]
    if any(c["value"] is not None for c in items_other):
        groups.append(
            {
                "key": "other",
                "item": "其他MPD",
                "name": "其他MPD",
                "condition": "库内其它 MPD/MPDin 实测",
                "unit": "nA",
                "children": items_other,
            }
        )
    out["MPD Dark Current"] = {
        "value": max(present) if present else None,
        "unit": "nA",
        "multi_all": True,
        "groups": groups,
    }

    # 6) 直接映射：ExtinctionRatio / heaterPPI
    for raw_key, item in tests.items():
        base = raw_key.split("@Chnl:")[0]
        canon = ITEM_ALIASES.get(base)
        if canon is None:
            for ak, av in ITEM_ALIASES.items():
                if ak.lower() == base.lower():
                    canon = av
                    break
        if canon and canon not in out and item.get("value") is not None:
            out[canon] = {"value": float(item["value"]), "unit": item.get("unit")}

    return out


def evaluate_die(
    tests: dict[str, dict[str, Any]],
    specs: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    按详情表固定顺序输出行；全部 Pass → 总体评价 Pass。
    表头字段：Item / Condition / Unit / Min / Target / Max / Note
    """
    normalized = normalize_tests(tests)
    spec_map = {s["name"]: s for s in specs}

    rows: list[dict[str, Any]] = []
    for meta in DETAIL_ROWS:
        key = meta["key"]
        spec = spec_map.get(key) or {}
        if spec and not spec.get("enabled", True):
            continue

        mn = spec["lsl"] if "lsl" in spec else meta["min"]
        tg = spec["target"] if spec.get("target") is not None else meta["target"]
        mx = spec["usl"] if "usl" in spec else meta["max"]

        item = normalized.get(key) or {}
        value = item.get("value")
        unit = item.get("unit") or meta["unit"]
        parts = item.get("parts") or {}
        children: list[dict[str, Any]] = []
        groups_out: list[dict[str, Any]] = []

        if key == "MPD Dark Current":
            # 限值：lsl/usl=1V，lsl_4v/usl_4v=4V；兼容旧模板拆行
            min_1v = spec.get("lsl") if "lsl" in spec else meta.get("min")
            max_1v = spec.get("usl") if spec.get("usl") is not None else meta.get("max", 50.0)
            min_4v = spec.get("lsl_4v") if "lsl_4v" in spec else meta.get("min_4v")
            max_4v = spec.get("usl_4v") if spec.get("usl_4v") is not None else meta.get("max_4v", 200.0)
            legacy1 = spec_map.get("MPD Dark Current @ 1.0V") or {}
            legacy4 = spec_map.get("MPD Dark Current @ 4.0V") or {}
            if "lsl" in legacy1:
                min_1v = legacy1.get("lsl")
            if legacy1.get("usl") is not None:
                max_1v = legacy1["usl"]
            if "lsl" in legacy4:
                min_4v = legacy4.get("lsl")
            if legacy4.get("usl") is not None:
                max_4v = legacy4["usl"]
            if legacy1 and not legacy1.get("enabled", True) and legacy4 and not legacy4.get("enabled", True):
                continue
            if spec and not spec.get("enabled", True) and not legacy1 and not legacy4:
                continue

            group_defs = item.get("groups") or []
            group_oks: list[bool] = []
            for g in group_defs:
                gkey = str(g.get("key") or "")
                is_other = gkey == "other"
                is_1v = gkey.startswith("1")
                gmin = None if is_other else (min_1v if is_1v else min_4v)
                gmax = None if is_other else (max_1v if is_1v else max_4v)
                items_out: list[dict[str, Any]] = []
                item_oks: list[bool] = []
                for ch in g.get("children") or []:
                    cv = ch.get("value")
                    if is_other and cv is None:
                        continue
                    cok = in_spec(cv, gmin, gmax)
                    if cok is None:
                        cok = False
                    item_oks.append(cok)
                    items_out.append(
                        {
                            "item": ch.get("item") or ch.get("name"),
                            "name": ch.get("item") or ch.get("name"),
                            "value": cv,
                            "unit": ch.get("unit") or unit,
                            "min": gmin,
                            "max": gmax,
                            "pass": cok,
                            "note": f"实测 {_fmt(cv)}" if cv is not None else "无实测",
                        }
                    )
                if is_other and not items_out:
                    continue
                gok = bool(item_oks) and all(item_oks)
                group_oks.append(gok)
                passed_n = sum(1 for x in items_out if x["pass"])
                groups_out.append(
                    {
                        "key": gkey,
                        "item": g.get("item") or gkey,
                        "name": g.get("name") or gkey,
                        "condition": g.get("condition") or "",
                        "unit": unit,
                        "min": gmin,
                        "max": gmax,
                        "pass": gok,
                        "note": f"{passed_n}/{len(items_out)} 项达标",
                        "children": items_out,
                        "is_group": True,
                    }
                )
            # 其他MPD 不参与 Pass；标准 1V/4V 全缺则 Fail
            judge_groups = [g for g in groups_out if g.get("key") != "other"]
            if judge_groups:
                ok = all(g["pass"] for g in judge_groups)
            else:
                ok = False
            children = groups_out
            mn, mx = None, None
            any_measured = any(
                ch.get("value") is not None
                for g in group_defs
                for ch in (g.get("children") or [])
            )
            if any_measured:
                note = "；".join(f"{g['item']} {g['note']}" for g in groups_out)
            else:
                note = "无实测（1311 下未读到 MPD-* / MPDin* ItemValue）"
            min_display = f"1V≥{_fmt(min_1v)} / 4V≥{_fmt(min_4v)}"
            max_display = f"1V≤{_fmt(max_1v)} / 4V≤{_fmt(max_4v)}"
        elif key == "MZM Loss":
            ok2 = in_spec(parts.get("OnChipLoss_2"), mn, mx) if parts else None
            ok3 = in_spec(parts.get("OnChipLoss_3"), mn, mx) if parts else None
            ok = (ok2 is True) and (ok3 is True)
            note = (
                f"OnChipLoss_2={_fmt(parts.get('OnChipLoss_2') if parts else None)}；"
                f"OnChipLoss_3={_fmt(parts.get('OnChipLoss_3') if parts else None)}"
            )
            max_display = mx
        elif key == "On Chip Loss + EC_EC Loss":
            ok = in_spec(value, mn, mx)
            if ok is None:
                ok = False
            note = (
                f"OnChipLoss={_fmt(parts.get('OnChipLoss') if parts else None)}；"
                f"EC-EC={_fmt(parts.get('EC-EC') if parts else None)}；"
                f"总和={_fmt(parts.get('sum') if parts else value)}"
            )
            max_display = mx
        elif key == "OutMPD Imbalance":
            ok = in_spec(value, mn, mx)
            if ok is None:
                ok = False
            if parts:
                note = (
                    f"OpticCurrMpdA={_fmt(parts.get('OpticCurrMpdA'))}；"
                    f"OpticCurrMpdB={_fmt(parts.get('OpticCurrMpdB'))}；"
                    f"结果={_fmt(value)}"
                )
            else:
                note = f"实测 {_fmt(value)}" if value is not None else "无实测"
            max_display = mx
        elif key == "InMPD Imbalance":
            ok = in_spec(value, mn, mx)
            if ok is None:
                ok = False
            if parts:
                note = (
                    f"MpdIn@5={_fmt(parts.get('OpitcCurrMpdIn@5'))}；"
                    f"MpdIn@1={_fmt(parts.get('OpitcCurrMpdIn@1'))}；"
                    f"Pin@5={_fmt(parts.get('InputPower@5'))}；"
                    f"Pin@1={_fmt(parts.get('InputPower@1'))}；"
                    f"结果={_fmt(value)}"
                )
            else:
                note = f"实测 {_fmt(value)}" if value is not None else "无实测"
            max_display = mx
        else:
            ok = in_spec(value, mn, mx)
            if ok is None:
                ok = False
            if value is not None:
                note = f"实测 {_fmt(value)}"
            else:
                hint = meta.get("db_hint") or spec.get("note") or ""
                note = f"无实测（未读到库字段{('：' + hint) if hint else ''}）"
            max_display = mx

        rows.append(
            {
                "key": key,
                "item": meta["item"],
                "name": meta["item"],
                "condition": meta["condition"],
                "unit": unit,
                "min": min_display if key == "MPD Dark Current" else mn,
                "target": tg,
                "max": max_display if key == "MPD Dark Current" else mx,
                "note": note,
                "value": value,
                "lsl": mn,
                "usl": mx,
                "pass": ok,
                "is_overall": False,
                "custom": False,
                "children": children,
                "groups": groups_out,
                "expandable": bool(children),
                "db_hint": meta.get("db_hint") or "",
            }
        )

    # 用户从数据库 ItemName 新增的自定义参数
    builtin_keys = {r["key"] for r in DETAIL_ROWS} | set(LEGACY_MPD_KEYS)
    for spec in specs:
        key = spec.get("name") or ""
        if not key or key in builtin_keys or key == "总体评价":
            continue
        if not spec.get("enabled", True):
            continue
        if any(r.get("key") == key for r in rows):
            continue

        mn = spec.get("lsl")
        tg = spec.get("target")
        mx = spec.get("usl")
        item = tests.get(key) or normalized.get(key) or {}
        value = item.get("value")
        unit = item.get("unit") or spec.get("unit")
        ok = in_spec(value, mn, mx)
        if ok is None:
            ok = False
        rows.append(
            {
                "key": key,
                "item": spec.get("display_name") or key,
                "name": spec.get("display_name") or key,
                "condition": spec.get("condition") or "",
                "unit": unit or "—",
                "min": mn,
                "target": tg,
                "max": mx,
                "note": f"实测 {_fmt(value)}" if value is not None else "无实测",
                "value": value,
                "lsl": mn,
                "usl": mx,
                "pass": ok,
                "is_overall": False,
                "custom": True,
                "children": [],
                "expandable": False,
            }
        )

    overall = bool(rows) and all(r["pass"] is True for r in rows)
    rows.append(
        {
            "key": "总体评价",
            "item": "总体评价",
            "name": "总体评价",
            "condition": "全部 Item 均为 Pass",
            "unit": "-",
            "min": None,
            "target": None,
            "max": None,
            "note": "—",
            "value": None,
            "lsl": None,
            "usl": None,
            "pass": overall,
            "is_overall": True,
            "children": [],
            "expandable": False,
        }
    )

    # 必须保留原始 ItemName→ItemValue，再叠加派生项；
    # 若只返回 normalized，库里的 LoopBack3/OnChipLoss 等实测会被丢掉，Note 全空。
    merged_tests = {**tests, **normalized}
    return {"pass": overall, "param_rows": rows, "tests": merged_tests}


def apply_derived(tests: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return normalize_tests(tests)


def summarize(
    dies: list[dict[str, Any]],
    specs: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(dies)
    pass_count = sum(1 for d in dies if d.get("pass"))
    fail_count = total - pass_count
    yield_pct = round(pass_count / total * 100, 2) if total else 0.0

    fail_by_param: dict[str, int] = {}
    labels: list[str] = []
    for meta in DETAIL_ROWS:
        labels.append(meta["key"])
        fail_by_param[meta["key"]] = 0

    for spec in specs:
        key = spec.get("name") or ""
        if key and key not in fail_by_param and key != "总体评价" and spec.get("enabled", True):
            fail_by_param[key] = 0
            labels.append(key)

    for die in dies:
        for row in die.get("param_rows") or []:
            if row.get("is_overall") or row.get("name") == "总体评价":
                continue
            key = row.get("key") or row.get("name")
            if key in fail_by_param and row.get("pass") is False:
                fail_by_param[key] += 1

    fail_rate_details = []
    for key in labels:
        fail_rate_details.append(
            {
                "name": key,
                "fail_count": fail_by_param.get(key, 0),
                "fail_rate": round(fail_by_param.get(key, 0) / total * 100, 2) if total else 0.0,
            }
        )

    return {
        "total": total,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "yield": yield_pct,
        "fail_rate_details": fail_rate_details,
    }
