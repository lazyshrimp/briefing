"""4% counts, breakout ratios, 60-day 25% counts, and the 52-week net.

Each count takes bars that already include ``volume``. A stock is left
out of that day's 4% or 25% counts when its volume is 0. The 4% rule uses
that stock's previous bar. The 25% rule uses the close on the session 60
places earlier in the passed trading calendar; a stock with no bar that
day is left out of both sides. That omission is not ``missing``.
``missing`` is reserved for a metric whose reads all failed. Names are not
filtered, so an ST stock stays in the universe.

新高减新低 is not computed here. The caller passes the value read from
Tongdaxin ``extdata_13``. Separate new-high and new-low counts are not
returned.
"""

from __future__ import annotations

MISSING = "missing"
NO_DOWN_4 = "no_down_4"
BUYERS_DOMINATE = "buyers_dominate"
FOUR_PCT = 0.04
TWENTY_FIVE_PCT = 0.25


def _through(bars: list[dict], on_date: str) -> list[dict]:
    return [bar for bar in bars if bar["date"] <= on_date]


def _bar_on(bars: list[dict], on_date: str) -> dict | None:
    for bar in reversed(bars):
        if bar["date"] == on_date:
            return bar
        if bar["date"] < on_date:
            return None
    return None


def _traded(bar: dict | None) -> bool:
    return bar is not None and int(bar["volume"]) > 0


def _session_before(trading_dates: list[str], on_date: str, lookback: int) -> str | None:
    """The session ``lookback`` places before ``on_date`` on the given calendar."""
    dates = [day for day in trading_dates if day <= on_date]
    if not dates or dates[-1] != on_date or len(dates) <= lookback:
        return None
    return dates[-(lookback + 1)]


def count_move(
    universe: list[dict],
    on_date: str,
    *,
    lookback: int,
    threshold: float,
    trading_dates: list[str] | None = None,
) -> dict[str, int]:
    """Count gains and losses against one earlier close.

    ``lookback`` 1 is the 4% rule: the previous bar in that stock's own file.
    Any other ``lookback`` is a session count on ``trading_dates``. For the
    25% rule that calendar is the Shanghai-Shenzhen 300 sessions, and the
    base close is the stock's bar on the session 60 places earlier. A stock
    with no bar on that session is left out of both sides.
    """
    ups = 0
    downs = 0
    base_date = None if lookback == 1 else _session_before(trading_dates or [], on_date, lookback)
    for stock in universe:
        window = _through(stock["bars"], on_date)
        today = _bar_on(window, on_date)
        if not _traded(today):
            continue
        if lookback == 1:
            if len(window) <= 1 or window[-1]["date"] != on_date:
                continue
            base = window[-2]["close"]
        else:
            if base_date is None:
                continue
            base_bar = _bar_on(window, base_date)
            if base_bar is None:
                continue
            base = base_bar["close"]
        if base <= 0:
            continue
        change = today["close"] / base - 1
        if change + 1e-12 >= threshold:
            ups += 1
        if change - 1e-12 <= -threshold:
            downs += 1
    return {"up": ups, "down": downs}


def ratio_from_counts(ups: list[int], downs: list[int]) -> dict:
    """Divide the summed counts. A zero down-sum is ``no_down_4``, not an error."""
    down_sum = sum(downs)
    if down_sum == 0:
        return {"value": None, "flag": NO_DOWN_4}
    value = sum(ups) / down_sum
    flag = BUYERS_DOMINATE if value > 1 else None
    return {"value": value, "flag": flag}


def _dates_ending(trading_dates: list[str], on_date: str, length: int) -> list[str] | None:
    dates = [day for day in trading_dates if day <= on_date]
    if not dates or dates[-1] != on_date or len(dates) < length:
        return None
    return dates[-length:]


def _metric_or_missing(universe: list[dict], read_failures: int, compute):
    if not universe and read_failures > 0:
        return MISSING
    return compute()


def _as_net(value: float | str | None) -> int | float | str:
    if value == MISSING or value is None:
        return MISSING
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def breadth_snapshot(
    universe: list[dict],
    on_date: str,
    trading_dates: list[str],
    *,
    new_high_net: float | str | None,
    read_failures: int = 0,
) -> dict:
    """One day's breadth. ``new_high_net`` is the extdata_13 difference."""
    net = _as_net(new_high_net)

    def four_pct() -> dict[str, int]:
        return count_move(universe, on_date, lookback=1, threshold=FOUR_PCT)

    counted = _metric_or_missing(universe, read_failures, four_pct)
    if counted == MISSING:
        up4: int | str = MISSING
        down4: int | str = MISSING
        ratio5: dict | str = MISSING
        ratio10: dict | str = MISSING
    else:
        up4 = counted["up"]
        down4 = counted["down"]
        ratio5 = _window_ratio(universe, on_date, trading_dates, 5)
        ratio10 = _window_ratio(universe, on_date, trading_dates, 10)

    quarter = _metric_or_missing(
        universe,
        read_failures,
        lambda: count_move(
            universe,
            on_date,
            lookback=60,
            threshold=TWENTY_FIVE_PCT,
            trading_dates=trading_dates,
        ),
    )
    if quarter == MISSING:
        up25: int | str = MISSING
        down25: int | str = MISSING
        diff25: int | str = MISSING
    else:
        up25 = quarter["up"]
        down25 = quarter["down"]
        diff25 = up25 - down25

    return {
        "net": net,
        "up4": up4,
        "down4": down4,
        "ratio5": ratio5,
        "ratio10": ratio10,
        "up25": up25,
        "down25": down25,
        "diff25": diff25,
    }


def _window_ratio(
    universe: list[dict],
    on_date: str,
    trading_dates: list[str],
    length: int,
) -> dict | str:
    days = _dates_ending(trading_dates, on_date, length)
    if days is None:
        return MISSING
    ups: list[int] = []
    downs: list[int] = []
    for day in days:
        counted = count_move(universe, day, lookback=1, threshold=FOUR_PCT)
        ups.append(counted["up"])
        downs.append(counted["down"])
    return ratio_from_counts(ups, downs)
