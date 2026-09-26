"""Reference values read straight from Tongdaxin files.

Nothing in this module imports the briefing calculation code. The formulas
follow the confirmed rules: 4% against each stock's own previous bar, 25%
against the close 60 Shanghai-Shenzhen 300 sessions earlier, volume 0 left
out, and industries limited to leaf T-codes.
"""

from __future__ import annotations

import struct
import sys
from datetime import date, timedelta
from pathlib import Path

class RecomputeError(Exception):
    """The reference recount cannot be finished from the given files."""


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
HS300_TOTAL = 300
RPS_EXT = {5: 11, 10: 7, 15: 12, 20: 8}
_WINDOW = 21
_IDX = 29
_DAT = 12


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
    if len(idx) < _IDX:
        return None
    count = struct.unpack_from("<I", idx, 25)[0]
    target = int(on_date.replace("-", ""))
    with dat_path.open("rb") as handle:
        raw = handle.read(count * _DAT)
    for point in range(count):
        off = point * _DAT
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
        raise RecomputeError("sh000300.day unreadable")
    dates = [day for day, _close, _volume in calendar if day <= on_date]
    if not dates or dates[-1] != on_date or len(dates) <= 60:
        raise RecomputeError(f"{on_date} is not 60 sessions into sh000300")
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
            "hs300": {"above": above["hs300"], "total": HS300_TOTAL},
            "chinext": {"above": above["chinext"], "total": chinext_total},
            "all_a": {"above": above["all_a"], "total": len(rows)},
        },
    }


def _text(path: Path) -> str:
    return path.read_bytes().decode("gbk", errors="replace")


def block_groups(tdx: Path) -> dict:
    """Leaf industries and ``#GN_`` concepts, in file order."""
    tdxzs = tdx / "T0002" / "hq_cache" / "tdxzs.cfg"
    incon = tdx / "incon.dat"
    infoharbor = tdx / "T0002" / "hq_cache" / "infoharbor_block.dat"
    chain: list[tuple[str, str]] = []
    for line in _text(incon).splitlines():
        parts = line.strip().split("|")
        if len(parts) >= 2 and parts[0].startswith("T") and parts[0][1:].isdigit() and parts[1]:
            chain.append((parts[0], parts[1]))
    codes = {code for code, _name in chain}
    industry_names = {
        name
        for code, name in chain
        if not any(other.startswith(code) and len(other) > len(code) for other in codes)
    }
    industry: list[dict] = []
    seen_codes: set[str] = set()
    for line in _text(tdxzs).splitlines():
        parts = line.strip().split("|")
        if len(parts) < 2:
            continue
        name, code = parts[0], parts[1]
        if name in industry_names and code not in seen_codes:
            seen_codes.add(code)
            industry.append({"code": code, "name": name})
    concept: list[dict] = []
    seen_concept: set[str] = set()
    for line in _text(infoharbor).splitlines():
        text = line.strip()
        if not text.startswith("#GN_"):
            continue
        parts = text[4:].split(",")
        if len(parts) < 3:
            continue
        name, code = parts[0], parts[2]
        if code.startswith("88") and code not in seen_concept:
            seen_concept.add(code)
            concept.append({"code": code, "name": name})
    return {"industry": industry, "concept": concept}


def _extdata_on(directory: Path, ext_num: int, on_date: str) -> dict[str, float]:
    idx_path = directory / f"extdata_{ext_num}.idx"
    dat_path = directory / f"extdata_{ext_num}.dat"
    if not idx_path.is_file() or not dat_path.is_file():
        return {}
    idx = idx_path.read_bytes()
    target = int(on_date.replace("-", ""))
    found: dict[str, float] = {}
    records = len(idx) // _IDX
    with dat_path.open("rb") as handle:
        for index in range(records):
            base = index * _IDX
            code = idx[base + 2 : base + 8].rstrip(b"\x00").decode("ascii", "replace")
            count = struct.unpack_from("<I", idx, base + 25)[0]
            raw = handle.read(count * _DAT)
            if not code or len(raw) < count * _DAT:
                continue
            for point in range(count):
                off = point * _DAT
                if struct.unpack_from("<I", raw, off)[0] == target:
                    found[code] = float(struct.unpack_from("<f", raw, off + 8)[0])
                    break
    return found


def _through(path: Path, on_date: str) -> list[tuple[str, float, int]] | None:
    bars = read_bars(path)
    if not bars:
        return None
    kept = [bar for bar in bars if bar[0] <= on_date]
    if not kept or kept[-1][0] != on_date:
        return None
    return kept


def _average(closes: list[float], window: int) -> float | None:
    if window <= 0 or len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def _yes_no(passed: bool) -> str:
    return "YES" if passed else "NO"


def _buy(closes: list[float]) -> str:
    if len(closes) < 20:
        return "missing"
    ma10 = _average(closes, 10)
    ma20 = _average(closes, 20)
    last = closes[-1]
    if ma10 is None or ma20 is None:
        return "missing"
    return _yes_no(last > ma10 and last > ma20 and ma10 > ma20)


def _weekly(bars: list[tuple[str, float, int]]) -> list[float]:
    by_week: dict[date, float] = {}
    for day, close, _volume in bars:
        current = date.fromisoformat(day)
        monday = current - timedelta(days=current.weekday())
        by_week[monday] = close
    return [by_week[key] for key in sorted(by_week)]


def _one_index(bars: list[tuple[str, float, int]] | None) -> dict[str, str]:
    if not bars:
        return {"daily_buy": "missing", "weekly_buy": "missing", "above_rising_ma5": "missing"}
    closes = [close for _day, close, _volume in bars]
    rising = "missing"
    if len(closes) >= 6:
        ma5 = _average(closes, 5)
        previous = _average(closes[:-1], 5)
        if ma5 is not None and previous is not None:
            rising = _yes_no(closes[-1] > ma5 and ma5 > previous)
    return {"daily_buy": _buy(closes), "weekly_buy": _buy(_weekly(bars)), "above_rising_ma5": rising}


def _interval(window: list[tuple[str, float, int]] | None, lookback: int) -> float | None:
    if window is None or len(window) <= lookback:
        return None
    base = window[-(lookback + 1)][1]
    if base <= 0:
        return None
    return window[-1][1] / base - 1


def _top(rows: list[dict], key: str) -> list[dict]:
    rows.sort(key=lambda row: row[key], reverse=True)
    return rows[:10]


def rank_reference(tdx: Path, on_date: str) -> dict:
    """Daily top 10 and the four RPS boards, values attached by code."""
    groups = block_groups(tdx)
    lday = tdx / "vipdoc" / "sh" / "lday"
    directory = tdx / "T0002" / "extdata"
    windows: dict[str, list[tuple[str, float, int]] | None] = {}

    def window(code: str) -> list[tuple[str, float, int]] | None:
        if code not in windows:
            bars = _through(lday / f"sh{code}.day", on_date)
            windows[code] = None if bars is None else bars[-_WINDOW:]
        return windows[code]

    def daily(names: list[dict]) -> list[dict]:
        rows = []
        for item in names:
            pct = _interval(window(item["code"]), 1)
            if pct is None:
                continue
            rows.append({"code": item["code"], "pct": pct})
        return _top(rows, "pct")

    rps_maps = {period: _extdata_on(directory, ext, on_date) for period, ext in RPS_EXT.items()}

    def rps_board(names: list[dict], period: int) -> list[dict]:
        values = rps_maps[period]
        rows = []
        for item in names:
            if item["code"] not in values:
                continue
            rows.append({"code": item["code"], "rps": values[item["code"]], "pct": _interval(window(item["code"]), period)})
        return _top(rows, "rps")

    return {
        "daily": {"industry": daily(groups["industry"]), "concept": daily(groups["concept"])},
        "rps": {
            kind: {period: rps_board(groups[kind], period) for period in RPS_EXT}
            for kind in ("industry", "concept")
        },
    }


def build_reference(tdx: str | Path, on_date: str) -> dict:
    """Signals, breadth counts, 50-day ratios, and rank boards for one date."""
    root = Path(tdx)
    counted = recount(root, on_date)
    hs300 = _through(root / "vipdoc" / "sh" / "lday" / "sh000300.day", on_date)
    chinext = _through(root / "vipdoc" / "sz" / "lday" / "sz399006.day", on_date)
    return {
        "signals": {"hs300": _one_index(hs300), "chinext": _one_index(chinext)},
        "ma50": counted["ma50"],
        "up4": counted["up4"],
        "down4": counted["down4"],
        "ratio5": counted["ratio5"],
        "ratio10": counted["ratio10"],
        "up25": counted["up25"],
        "down25": counted["down25"],
        "ranks": rank_reference(root, on_date),
    }
