"""Industry and concept top-10 boards.

The daily board sorts by the block index's own previous bar.
The 5/10/15/20-day boards sort only by Tongdaxin RPS.
The interval change is written beside the name and never breaks a tie.
"""

from __future__ import annotations

from pathlib import Path

from briefing.tdx.day import MISSING, read_day_bars
from briefing.tdx.extdata import read_extdata_series

SHORT_LIST = "short_list"
TOP_N = 10
RPS_EXT = {5: 11, 10: 7, 15: 12, 20: 8}
_WINDOW_BARS = 21


def _board(items: list[dict]) -> dict:
    ranked = items[:TOP_N]
    board = {"items": ranked}
    if len(items) < TOP_N:
        board["flag"] = SHORT_LIST
    return board


def _bars_through(lday_dir: Path, code: str, on_date: str) -> list[dict] | None:
    """Bars on or before ``on_date``, ending on that date, at most 21 bars.

    The slice is taken after dropping later bars, so a replay of an older
    session does not depend on whatever the file's last record is.
    """
    bars = read_day_bars(lday_dir / f"sh{code}.day")
    if bars == MISSING or not isinstance(bars, list):
        return None
    window = [bar for bar in bars if bar["date"] <= on_date]
    if not window or window[-1]["date"] != on_date:
        return None
    return window[-_WINDOW_BARS:]


def _interval_pct(window: list[dict] | None, lookback: int) -> float | str:
    if window is None or len(window) <= lookback:
        return MISSING
    base = window[-(lookback + 1)]["close"]
    if base <= 0:
        return MISSING
    return window[-1]["close"] / base - 1


def daily_top10(groups: dict, lday_dir: str | Path, on_date: str) -> dict:
    """Top 10 by today's own-bar change. Industry and concept stay separate."""
    root = Path(lday_dir)

    def one(names: list[dict]) -> dict:
        def score(item: dict) -> float | None:
            change = _interval_pct(_bars_through(root, item["code"], on_date), 1)
            if change == MISSING:
                return None
            return float(change)

        def decorate(item: dict, change: float) -> dict:
            return {"name": item["name"], "code": item["code"], "pct": change}

        rows: list[dict] = []
        for item in names:
            change = score(item)
            if change is None:
                continue
            rows.append(decorate(item, change))
        rows.sort(key=lambda row: row["pct"], reverse=True)
        return _board(rows)

    return {
        "industry": one(groups.get("industry") or []),
        "concept": one(groups.get("concept") or []),
    }


def rps_top10(
    groups: dict,
    lday_dir: str | Path,
    extdata_dir: str | Path,
    on_date: str,
) -> dict:
    """Four RPS boards for industry and four for concept.

    Order is the extdata value, highest first. Equal RPS values keep the
    incoming order. A missing interval change stays on the board as ``missing``.
    """
    root = Path(lday_dir)
    directory = Path(extdata_dir)
    bars_cache: dict[str, list[dict] | None] = {}

    def cached_bars(code: str) -> list[dict] | None:
        if code not in bars_cache:
            bars_cache[code] = _bars_through(root, code, on_date)
        return bars_cache[code]

    def one(names: list[dict], period: int) -> dict:
        ext_num = RPS_EXT[period]

        def score(item: dict) -> float | None:
            value = read_extdata_series(directory, ext_num, item["code"], on_date)
            if value == MISSING:
                return None
            return float(value)

        def decorate(item: dict, rps: float) -> dict:
            change = _interval_pct(cached_bars(item["code"]), period)
            return {"name": item["name"], "code": item["code"], "pct": change, "rps": rps}

        rows: list[dict] = []
        for item in names:
            scored = score(item)
            if scored is None:
                continue
            rows.append(decorate(item, scored))
        rows.sort(key=lambda row: row["rps"], reverse=True)
        return _board(rows)

    return {
        kind: {period: one(groups.get(kind) or [], period) for period in RPS_EXT}
        for kind in ("industry", "concept")
    }
