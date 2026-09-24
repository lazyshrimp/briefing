"""Three YES/NO signals for one index close series.

Daily and weekly buy require close above both the 10-period and 20-period
simple moving averages, and the 10-period average above the 20-period average.
Weekly closes are the last trading day inside each Monday-Friday week.

Above a rising 5-day average requires close above today's MA5, and today's
MA5 above the previous trading day's MA5. Equality is NO. A series that is
too short yields ``missing`` for that signal only.
"""

from __future__ import annotations

from datetime import date, timedelta

YES = "YES"
NO = "NO"
MISSING = "missing"


def moving_average(closes: list[float], window: int) -> float | None:
    """Simple average of the last ``window`` closes, or ``None`` if shorter."""
    if window <= 0 or len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def _week_monday(iso_date: str) -> date:
    current = date.fromisoformat(iso_date)
    return current - timedelta(days=current.weekday())


def weekly_closes(bars: list[dict]) -> list[float]:
    """Last close of each Monday-Friday week. ``bars`` must be ascending."""
    by_week: dict[date, float] = {}
    for bar in bars:
        by_week[_week_monday(bar["date"])] = bar["close"]
    return [by_week[key] for key in sorted(by_week)]


def _yes_no(passed: bool) -> str:
    return YES if passed else NO


def _buy_signal(closes: list[float]) -> str:
    if len(closes) < 20:
        return MISSING
    ma10 = moving_average(closes, 10)
    ma20 = moving_average(closes, 20)
    last = closes[-1]
    assert ma10 is not None and ma20 is not None
    return _yes_no(last > ma10 and last > ma20 and ma10 > ma20)


def index_signals(bars: list[dict]) -> dict[str, str]:
    """Return ``daily_buy``, ``weekly_buy``, and ``above_rising_ma5``."""
    closes = [bar["close"] for bar in bars]
    rising = MISSING
    if len(closes) >= 6:
        ma5 = moving_average(closes, 5)
        previous = moving_average(closes[:-1], 5)
        assert ma5 is not None and previous is not None
        rising = _yes_no(closes[-1] > ma5 and ma5 > previous)
    return {
        "daily_buy": _buy_signal(closes),
        "weekly_buy": _buy_signal(weekly_closes(bars)),
        "above_rising_ma5": rising,
    }
