"""生成按 Die（Shot+SN）粒度的 Mock EAV。"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent

# 保证可从 backend 同级导入结构；此处内联流水号避免跨包
DIE_SERIALS = [
    "0101", "0102", "0103", "0104", "0105", "0106",
    "0201", "0202", "0204", "0205", "0206",
    "0301", "0302", "0303", "0304", "0305", "0306",
]

MPD_1V = [*(f"MPD-{ch}{ab}--1" for ch in range(1, 9) for ab in ("A", "B")), "MPDin--1", "MPDin2--1"]
MPD_4V = [*(f"MPD-{ch}{ab}--4" for ch in range(1, 9) for ab in ("A", "B")), "MPDin--4", "MPDin2--4"]


def _sn(x: int, y: int, serial: str) -> str:
    return f'"({x},{y})"$$SN{serial}'


def _row(
    head_id: int,
    wafer: str,
    shot: int,
    sn: str,
    create_time: str,
    name: str,
    unit: str,
    value: float,
    chnl: str | None = None,
    wavelength: str = "1311",
) -> dict:
    r = {
        "HeadID": head_id,
        "Wafer": wafer,
        "Shot": str(shot),
        "SN": sn,
        "CreateTime": create_time,
        "ItemName": name,
        "Itenunit": unit,
        "ItemUnit": unit,
        "Itemvalue": value,
        "ItemValue": value,
        "WaveLength": wavelength,
    }
    if chnl is not None:
        r["Chnl"] = chnl
    return r


def gen_die_rows(
    head_id: int,
    wafer: str,
    shot: int,
    sn: str,
    create_time: str,
    rng: random.Random,
) -> list[dict]:
    """按 Die 独立造数；单颗不良率约 8%，使 Shot 全 Pass 比例约六成。"""
    rows: list[dict] = []
    # 约 8% Die 注入不良（同 Shot 内可有绿有红，整体 Shot 约 60% 全绿）
    force_fail = rng.random() < 0.08
    on_chip = rng.uniform(4.0, 8.0)
    ec = rng.uniform(3.0, 6.0)
    if force_fail and rng.random() < 0.25:
        on_chip, ec = 9.0, 8.0
    mzm2 = rng.uniform(5.0, 6.0) if force_fail and rng.random() < 0.2 else rng.uniform(2.5, 4.5)
    mzm3 = rng.uniform(5.0, 6.0) if force_fail and rng.random() < 0.15 else rng.uniform(2.5, 4.5)
    if force_fail and rng.random() < 0.2:
        out_imb_db = rng.choice([-1.4, 1.5])
    else:
        out_imb_db = rng.uniform(-0.7, 0.7)
    out_b, out_a = 1.0, 1.0 * (10 ** (out_imb_db / 10.0))
    if force_fail and rng.random() < 0.2:
        target_in = rng.choice([-1.5, 1.4])
    else:
        target_in = rng.uniform(-0.6, 0.6)
    pin1, pin5 = 0.0, 0.2
    ratio_db = target_in + (pin5 - pin1)
    in1, in5 = 1.0, 1.0 * (10 ** (ratio_db / 10.0))
    dark1_fail = force_fail and rng.random() < 0.25
    dark4_fail = force_fail and rng.random() < 0.2
    er = rng.uniform(18, 23) if force_fail and rng.random() < 0.25 else rng.uniform(25, 32)
    heater = rng.uniform(15, 18) if force_fail and rng.random() < 0.2 else rng.uniform(9, 13.5)

    def add(name: str, unit: str, value: float, chnl: str | None = None) -> None:
        rows.append(_row(head_id, wafer, shot, sn, create_time, name, unit, value, chnl=chnl))

    add("OnChipLoss", "dB", on_chip)
    add("EC-EC", "dB", ec)
    add("OnChipLoss_2", "dB", mzm2, "1")
    add("OnChipLoss_3", "dB", mzm3, "1")
    add("OpticCurrMpdA", "A", out_a)
    add("OpticCurrMpdB", "A", out_b)
    add("OpitcCurrMpdIn", "A", in5, "5")
    add("OpitcCurrMpdIn", "A", in1, "1")
    add("InputPower", "dBm", pin5, "5")
    add("InputPower", "dBm", pin1, "1")
    add("ExtinctionRatio", "dB", er)
    add("heaterPPI", "mW", heater)
    for name in MPD_1V:
        v = rng.uniform(60, 120) if dark1_fail and name.endswith("A--1") else rng.uniform(10, 45)
        add(name, "nA", v)
    for name in MPD_4V:
        v = rng.uniform(220, 280) if dark4_fail and name.endswith("A--4") else rng.uniform(80, 180)
        add(name, "nA", v)
    return rows


def main() -> None:
    rng = random.Random(42)
    rows: list[dict] = []
    head_id = 1
    base_time = datetime(2026, 8, 1, 9, 0, 0)

    # 圆形有效位：每行 5,7,7,7,5,3；Shot=列*10+行，列在 10 宽内居中
    row_counts = {1: 5, 2: 7, 3: 7, 4: 7, 5: 5, 6: 3}
    shots: list[tuple[int, int, int]] = []  # shot, col, row
    for row, n in row_counts.items():
        start = (10 - n) // 2 + 1
        for col in range(start, start + n):
            shots.append((col * 10 + row, col, row))

    for shot, col, row in shots:
        serials = DIE_SERIALS if shot in {31, 45, 56, 82} else rng.sample(DIE_SERIALS, k=5)
        for serial in serials:
            sn = _sn(col, row, serial)
            ct = (base_time + timedelta(minutes=head_id)).strftime("%Y-%m-%d %H:%M:%S")
            rows.extend(gen_die_rows(head_id, "DR4-5-26", shot, sn, ct, rng))
            head_id += 1

    for shot, col, row in shots[:8]:
        for serial in DIE_SERIALS[:4]:
            sn = _sn(col, row, serial)
            ct = (base_time + timedelta(days=1, minutes=head_id)).strftime("%Y-%m-%d %H:%M:%S")
            rows.extend(gen_die_rows(head_id, "DR4-5-27", shot, sn, ct, rng))
            head_id += 1

    out = ROOT / "eav_rows.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} rows, shots={len(shots)}, heads≈{head_id - 1} -> {out}")


if __name__ == "__main__":
    main()
