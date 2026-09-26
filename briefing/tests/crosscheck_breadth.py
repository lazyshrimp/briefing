"""Recount 2026-09-23 breadth without using breadth.py to count.

The script reads ``.day`` and extdata through ``recompute.py``, then
compares that recount with ``breadth_snapshot``. A mismatch is printed
and the process exits 1. ``--write-golden`` freezes the recount only
after the two sides agree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from briefing.evaluation.recompute import RecomputeError, recount

TDX = Path(r"C:\zd_pazq_hy")
ON_DATE = "2026-09-23"
GOLDEN = Path(__file__).parent / "fixtures" / "golden_breadth_20260923.json"


def _flag(up: int, down: int) -> dict:
    if down == 0:
        return {"value": None, "flag": "no_down_4"}
    value = up / down
    return {"value": value, "flag": "buyers_dominate" if value > 1 else None}


def _same(left, right) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        return left is not None and right is not None and float(left) == float(right)
    return left == right


def compare(counted: dict, on_date: str) -> list[str]:
    from briefing.analysis.breadth import breadth_snapshot
    from briefing.analysis.ma50 import a_share_denominators, ma50_ratios
    from briefing.tdx.day import read_day_bars
    from briefing.tdx.extdata import read_market_extdata, read_new_high_net
    from briefing.tdx.universe import load_a_share_universe

    calendar = read_day_bars(TDX / "vipdoc" / "sh" / "lday" / "sh000300.day")
    trading_dates = [bar["date"] for bar in calendar if bar["date"] <= on_date]
    universe, failures = load_a_share_universe(TDX, on_date)
    snapshot = breadth_snapshot(
        universe,
        on_date,
        trading_dates,
        new_high_net=read_new_high_net(TDX / "T0002" / "extdata", on_date),
        read_failures=failures,
    )
    denoms = a_share_denominators(TDX)
    ratios = ma50_ratios(
        hs300_above=read_market_extdata(TDX / "T0002" / "extdata", 5, on_date),
        hs300_total=denoms["hs300"],
        chinext_above=read_market_extdata(TDX / "T0002" / "extdata", 6, on_date),
        chinext_total=denoms["chinext"],
        all_a_above=read_market_extdata(TDX / "T0002" / "extdata", 4, on_date),
        all_a_total=denoms["all_a"],
    )
    diffs: list[str] = []
    for key in ("net", "up4", "down4", "up25", "down25", "diff25"):
        if not _same(counted[key], snapshot[key]):
            diffs.append(f"{key}: recount {counted[key]} snapshot {snapshot[key]}")
    for key in ("ratio5", "ratio10"):
        expected = _flag(counted[key]["up"], counted[key]["down"])
        if snapshot[key] != expected:
            diffs.append(f"{key}: recount {expected} snapshot {snapshot[key]}")
    for name in ("hs300", "chinext", "all_a"):
        got = ratios[name]
        want_above = counted["ma50"][name]["above"]
        want_total = counted["ma50"][name]["total"]
        if not isinstance(got, dict) or not _same(got["above"], want_above) or got["total"] != want_total:
            diffs.append(f"ma50 {name}: recount {counted['ma50'][name]} snapshot {got}")
    return diffs


def main() -> int:
    on_date = next((arg for arg in sys.argv[1:] if arg.startswith("20")), ON_DATE)
    try:
        counted = recount(TDX, on_date)
    except RecomputeError as exc:
        print(f"RecomputeError: {exc}", file=sys.stderr)
        return 1
    diffs = compare(counted, on_date)
    if diffs:
        print("mismatch")
        for line in diffs:
            print(line)
        return 1
    print(json.dumps(counted, ensure_ascii=False, indent=2))
    if "--write-golden" in sys.argv and on_date == ON_DATE:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(counted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
