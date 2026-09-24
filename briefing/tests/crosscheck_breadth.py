"""Recount 2026-09-23 breadth without using breadth.py to count.

The script reads ``.day`` and extdata with ``struct`` on its own, then
compares that recount with ``breadth_snapshot``. A mismatch is printed
and the process exits 1. ``--write-golden`` freezes the recount only
after the two sides agree.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TDX = Path(r"C:\zd_pazq_hy")
ON_DATE = "2026-09-23"
RECORD = struct.Struct("<IIIIIfII")
PREFIXES = (
    "600",
    "601",
    "603",
    "605",
    "688",
    "689",
    "000",
    "001",
    "002",
    "003",
    "300",
    "301",
    "302",
)
CHINEXT = ("300", "301", "302")
FOUR = 0.04
QUARTER = 0.25
GOLDEN = Path(__file__).parent / "fixtures" / "golden_breadth_20260923.json"


def _iso(date_int: int) -> str:
    return f"{date_int // 10000:04d}-{(date_int % 10000) // 100:02d}-{date_int % 100:02d}"


def read_bars(path: Path) -> list[tuple[str, float, int]] | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if not raw or len(raw) % RECORD.size != 0:
        return None
    bars: list[tuple[str, float, int]] = []
    previous: str | None = None
    for offset in range(0, len(raw), RECORD.size):
        date_int, _open, _high, _low, close, _amount, volume, _reserved = RECORD.unpack_from(raw, offset)
        day = _iso(date_int)
        if previous is not None and day <= previous:
            return None
        previous = day
        bars.append((day, close / 100.0, int(volume)))
    return bars


def quote_rows(tdx: Path) -> list[tuple[str, str]]:
    path = tdx / "T0002" / "hq_cache" / "specgpext.txt"
    text = path.read_bytes().decode("gbk", "replace")
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        market, code, *_rest = line.split("|")
        if market not in {"0", "1"}:
            continue
        if len(code) != 6 or not code.isdigit() or not code.startswith(PREFIXES):
            continue
        if code in seen:
            continue
        seen.add(code)
        rows.append((market, code))
    return rows


def first_extdata(tdx: Path, ext_num: int, on_date: str) -> float | None:
    directory = tdx / "T0002" / "extdata"
    idx = (directory / f"extdata_{ext_num}.idx").read_bytes()
    dat_path = directory / f"extdata_{ext_num}.dat"
    if len(idx) < 29:
        return None
    count = struct.unpack_from("<I", idx, 25)[0]
    target = int(on_date.replace("-", ""))
    with dat_path.open("rb") as handle:
        raw = handle.read(count * 12)
    for point in range(count):
        off = point * 12
        if struct.unpack_from("<I", raw, off)[0] == target:
            return float(struct.unpack_from("<f", raw, off + 8)[0])
    return None


def _whole(value: float) -> int | float:
    if float(value).is_integer():
        return int(value)
    return float(value)


def recount(tdx: Path, on_date: str) -> dict:
    calendar = read_bars(tdx / "vipdoc" / "sh" / "lday" / "sh000300.day")
    if not calendar:
        raise SystemExit("sh000300.day unreadable")
    dates = [day for day, _close, _volume in calendar if day <= on_date]
    if not dates or dates[-1] != on_date or len(dates) <= 60:
        raise SystemExit(f"{on_date} is not 60 sessions into sh000300")
    base = dates[-61]
    window = dates[-10:]
    needed = set(window)
    rows = quote_rows(tdx)
    stocks: list[tuple[list[str], list[float], list[int]]] = []
    for index, (market, code) in enumerate(rows, start=1):
        folder = "sz" if market == "0" else "sh"
        bars = read_bars(tdx / "vipdoc" / folder / "lday" / f"{folder}{code}.day")
        if bars is None:
            continue
        kept = [bar for bar in bars if bar[0] <= on_date]
        stocks.append(([bar[0] for bar in kept], [bar[1] for bar in kept], [bar[2] for bar in kept]))
        if index % 1000 == 0:
            print(f"read {index}", file=sys.stderr)
    print(f"read {len(rows)} quote codes, {len(stocks)} day files", file=sys.stderr)

    def locate(dates_of: list[str], day: str) -> int | None:
        lo = 0
        hi = len(dates_of)
        while lo < hi:
            mid = (lo + hi) // 2
            if dates_of[mid] < day:
                lo = mid + 1
            else:
                hi = mid
        if lo < len(dates_of) and dates_of[lo] == day:
            return lo
        return None

    def count_4(day: str) -> tuple[int, int]:
        ups = 0
        downs = 0
        for dates_of, closes, volumes in stocks:
            at = locate(dates_of, day)
            if at is None or at == 0 or volumes[at] <= 0 or closes[at - 1] <= 0:
                continue
            change = closes[at] / closes[at - 1] - 1
            if change + 1e-12 >= FOUR:
                ups += 1
            if change - 1e-12 <= -FOUR:
                downs += 1
        return ups, downs

    up4, down4 = count_4(on_date)
    ratio_days = {day: count_4(day) for day in needed}
    up25 = 0
    down25 = 0
    for dates_of, closes, volumes in stocks:
        today = locate(dates_of, on_date)
        base_at = locate(dates_of, base)
        if today is None or base_at is None or volumes[today] <= 0 or closes[base_at] <= 0:
            continue
        change = closes[today] / closes[base_at] - 1
        if change + 1e-12 >= QUARTER:
            up25 += 1
        if change - 1e-12 <= -QUARTER:
            down25 += 1

    def ratio(days: list[str]) -> dict:
        ups = sum(ratio_days[day][0] for day in days)
        downs = sum(ratio_days[day][1] for day in days)
        return {"up": ups, "down": downs}

    net = first_extdata(tdx, 13, on_date)
    above = {name: first_extdata(tdx, ext, on_date) for name, ext in (("hs300", 5), ("chinext", 6), ("all_a", 4))}
    chinext_total = sum(code.startswith(CHINEXT) for _market, code in rows)
    return {
        "date": on_date,
        "base_date": base,
        "net": None if net is None else _whole(net),
        "up4": up4,
        "down4": down4,
        "ratio5": ratio(dates[-5:]),
        "ratio10": ratio(dates[-10:]),
        "up25": up25,
        "down25": down25,
        "diff25": up25 - down25,
        "ma50": {
            "hs300": {"above": above["hs300"], "total": 300},
            "chinext": {"above": above["chinext"], "total": chinext_total},
            "all_a": {"above": above["all_a"], "total": len(rows)},
        },
    }


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
    counted = recount(TDX, on_date)
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
