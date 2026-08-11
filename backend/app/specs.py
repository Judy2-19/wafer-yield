"""DR8-PIC 规格行（详情表顺序）与库字段别名。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Condition 中的下标用 HTML：V<sub>R,MOD</sub> / P<sub>in</sub> / V<sub>R,MPD</sub>
COND_VR_MOD = "V<sub>R,MOD</sub> = 0.0V, P<sub>in</sub> = 6 dBm, Wavelength: 1311nm"
COND_VR_MPD_1 = "V<sub>R,MPD</sub> = 1.0V"
COND_VR_MPD_4 = "V<sub>R,MPD</sub> = 4.0V"

# MPD Dark Current：详情只显示 1V / 4V 两行，子项见 3d711.png
MPD_DARK_1V_ITEMS: list[str] = [
    *(f"MPD-{ch}{ab}--1" for ch in range(1, 9) for ab in ("A", "B")),
    "MPDin--1",
    "MPDin2--1",
]
MPD_DARK_4V_ITEMS: list[str] = [
    *(f"MPD-{ch}{ab}--4" for ch in range(1, 9) for ab in ("A", "B")),
    "MPDin--4",
    "MPDin2--4",
]

# 详情页固定顺序（MPD Dark Current 拆两行）
DETAIL_ROWS: list[dict[str, Any]] = [
    {
        "key": "On Chip Loss + EC_EC Loss",
        "item": "On Chip Loss + EC_EC Loss",
        "condition": COND_VR_MOD,
        "unit": "dB",
        "min": None,
        "target": None,
        "max": 14.4,
        "note": "",
        # 库字段：OnChipLoss + EC-EC，判定用总和
        "db_hint": "OnChipLoss + EC-EC",
    },
    {
        "key": "MZM Loss",
        "item": "MZM Loss",
        "condition": COND_VR_MOD,
        "unit": "dB",
        "min": None,
        "target": None,
        "max": 4.9,
        "note": "",
        # 库字段：OnChipLoss_2、OnChipLoss_3，二者都合格才 Pass
        "db_hint": "OnChipLoss_2 & OnChipLoss_3",
    },
    {
        "key": "OutMPD Imbalance",
        "item": "OutMPD Imbalance",
        "condition": COND_VR_MOD,
        "unit": "dB",
        "min": -1.0,
        "target": None,
        "max": 1.0,
        "note": "",
        "db_hint": "10*log10(OpticCurrMpdA/OpticCurrMpdB)",
    },
    {
        "key": "InMPD Imbalance",
        "item": "InMPD Imbalance",
        "condition": COND_VR_MOD,
        "unit": "dB",
        "min": -1.0,
        "target": None,
        "max": 1.0,
        "note": "",
        "db_hint": "10*log10(OpitcCurrMpdIn@5/OpitcCurrMpdIn@1)-(InputPower@5-InputPower@1)",
    },
    {
        "key": "MPD Dark Current",
        "item": "MPD Dark Current",
        "condition": f"{COND_VR_MPD_1} / {COND_VR_MPD_4}",
        "unit": "nA",
        "min": None,  # 1.0V 组 Min
        "min_4v": None,  # 4.0V 组 Min
        "target": None,
        "max": 50.0,  # 1.0V 组 Max
        "max_4v": 200.0,  # 4.0V 组 Max
        "note": "",
        "db_hint": "1V/4V 两组全部子项达标才 Pass",
    },
    {
        "key": "MOD ON_OFF Extinction Ratio",
        "item": "MOD ON_OFF Extinction Ratio",
        "condition": COND_VR_MOD,
        "unit": "dB",
        "min": 24.0,
        "target": 30.0,
        "max": None,
        "note": "",
        "db_hint": "ExtinctionRatio",
    },
    {
        "key": "Heater Pi Shift Power",
        "item": "Heater Pi Shift Power",
        "condition": "",
        "unit": "mW",
        "min": None,
        "target": 10.0,
        "max": 14.5,
        "note": "",
        "db_hint": "heaterPPI",
    },
]

SPEC_NAMES = [r["key"] for r in DETAIL_ROWS]

# 库内 ItemName → 标准展示 key（仅直接映射项；派生项在 judge 中计算）
ITEM_ALIASES: dict[str, str] = {
    "ExtinctionRatio": "MOD ON_OFF Extinction Ratio",
    "MOD ON_OFF Extinction Ratio": "MOD ON_OFF Extinction Ratio",
    "MODON_OFFExtinctionRatio": "MOD ON_OFF Extinction Ratio",
    "heaterPPI": "Heater Pi Shift Power",
    "heaterppi": "Heater Pi Shift Power",
    "HeaterPPI": "Heater Pi Shift Power",
    "Heater Pi Shift Power": "Heater Pi Shift Power",
    "HeaterPiShiftPower": "Heater Pi Shift Power",
}

DR8_PIC_TEMPLATE: dict[str, Any] = {
    "id": "dr8-pic",
    "name": "DR8-PIC 客户标准（默认）",
    "builtin": True,
    "specs": [
        {
            "name": r["key"],
            "display_name": r["item"],
            "condition": r["condition"],
            "lsl": r["min"],
            "lsl_4v": r.get("min_4v"),
            "target": r["target"],
            "usl": r["max"],
            "usl_4v": r.get("max_4v"),
            "enabled": True,
            "unit": r["unit"],
            "note": r["note"],
            "custom": False,
        }
        for r in DETAIL_ROWS
    ],
}

# 旧模板拆行 key，判定时并入「MPD Dark Current」
LEGACY_MPD_KEYS = frozenset({"MPD Dark Current @ 1.0V", "MPD Dark Current @ 4.0V"})

BUILTIN_TEMPLATE_IDS = frozenset({"dr8-pic"})


def list_templates() -> list[dict[str, Any]]:
    return [deepcopy(DR8_PIC_TEMPLATE)]


def get_template(template_id: str) -> dict[str, Any] | None:
    for t in list_templates():
        if t["id"] == template_id:
            return t
    return None


def is_builtin_template(template_id: str) -> bool:
    return template_id in BUILTIN_TEMPLATE_IDS
