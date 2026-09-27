"""D3: one snapshot from records D2 already loaded.

The skill calls the existing tools in a fixed order. It does not keep a
second copy of their formulas. A missing series stays missing. The index
session not matching the target date stops the snapshot.
"""

from __future__ import annotations

from briefing.analysis.breadth import breadth_snapshot
from briefing.analysis.ma50 import ma50_ratios
from briefing.analysis.ranks import daily_top10, rps_top10
from briefing.analysis.signals import index_signals
from briefing.core.models import Snapshot

STOP = "stop"
_MISSING = "missing"
_SIGNAL_FIELDS = ("daily_buy", "weekly_buy", "above_rising_ma5")


def compute_snapshot(raw: dict) -> Snapshot | str:
    """Return the D3 snapshot, or ``stop`` when the index date does not match."""
    on_date = raw["on_date"]
    hs300 = raw.get("hs300_bars")
    if not _ends_on(hs300, on_date):
        return STOP
    signals = {
        "hs300": index_signals(hs300),
        "chinext": _index_or_missing(raw.get("chinext_bars"), on_date),
    }
    denominators = raw.get("denominators")
    if not isinstance(denominators, dict):
        denominators = {key: _MISSING for key in ("hs300", "chinext", "all_a")}
    ma50 = ma50_ratios(
        hs300_above=raw.get("hs300_above"),
        hs300_total=denominators.get("hs300"),
        chinext_above=raw.get("chinext_above"),
        chinext_total=denominators.get("chinext"),
        all_a_above=raw.get("all_a_above"),
        all_a_total=denominators.get("all_a"),
    )
    breadth = breadth_snapshot(
        list(raw.get("universe") or []),
        on_date,
        list(raw.get("trading_dates") or []),
        new_high_net=raw.get("new_high_net"),
        read_failures=int(raw.get("read_failures") or 0),
    )
    groups = raw.get("groups")
    if isinstance(groups, dict):
        lday = raw["lday_dir"]
        extdata = raw["extdata_dir"]
        ranks = {
            "daily": daily_top10(groups, lday, on_date),
            "rps": rps_top10(groups, lday, extdata, on_date),
        }
    else:
        ranks = _MISSING
    return Snapshot(
        on_date=on_date,
        signals=signals,
        breadth=breadth,
        ma50=ma50,
        ranks=ranks,
    )


def _ends_on(bars: object, on_date: str) -> bool:
    return isinstance(bars, list) and bool(bars) and bars[-1]["date"] == on_date


def _index_or_missing(bars: object, on_date: str) -> dict[str, str]:
    if not _ends_on(bars, on_date):
        return {field: _MISSING for field in _SIGNAL_FIELDS}
    return index_signals(bars)
