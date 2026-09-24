"""Decide whether a date is a trading day from the index day file."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from briefing.tdx.day import MISSING, read_day_bars, to_date_str

TRADING_DAY = "trading_day"
SKIP = "skip"
STOP = "stop"


def is_trading_day(on_date: date | datetime | str | int, index_day_path: str | Path) -> str:
    """Return ``trading_day``, ``skip``, or ``stop``.

    The date is a trading day when it appears in ``sh000300.day``. A date
    that is absent is ``skip``. A missing or unreadable file is ``stop``.
    """
    bars = read_day_bars(index_day_path)
    if bars == MISSING:
        return STOP
    target = to_date_str(on_date)
    if any(bar["date"] == target for bar in bars):
        return TRADING_DAY
    return SKIP
