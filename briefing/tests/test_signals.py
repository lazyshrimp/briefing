"""YES/NO boundaries, plus a hand-checked MA on the local index file."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from briefing.analysis.signals import index_signals, moving_average
from briefing.tdx.day import read_day_bars

TDX = Path(r"C:\zd_pazq_hy")
FIXTURES = Path(__file__).parent / "fixtures"
live = pytest.mark.skipif(not (TDX / "vipdoc" / "sh" / "lday" / "sh000300.day").is_file(), reason="skip")


def _bars(closes: list[float], start: str = "2026-01-05") -> list[dict]:
    current = date.fromisoformat(start)
    bars = []
    for close in closes:
        bars.append({"date": current.isoformat(), "close": close})
        current += timedelta(days=1)
    return bars


def _fridays(closes: list[float], start: str = "2026-01-02") -> list[dict]:
    current = date.fromisoformat(start)
    bars = []
    for close in closes:
        bars.append({"date": current.isoformat(), "close": close})
        current += timedelta(days=7)
    return bars


def test_daily_buy_yes_and_no() -> None:
    yes_closes = [1.0] * 10 + [3.0] * 9 + [4.0]
    yes = index_signals(_bars(yes_closes))
    assert yes["daily_buy"] == "YES"

    no_closes = [5.0] * 10 + [1.0] * 9 + [4.0]
    no = index_signals(_bars(no_closes))
    assert no["daily_buy"] == "NO"

    tied = [1.0] * 19 + [1.0]
    assert index_signals(_bars(tied))["daily_buy"] == "NO"


def test_rising_ma5_and_short_series() -> None:
    rising = index_signals(_bars([1, 1, 1, 1, 1, 3]))
    assert rising["above_rising_ma5"] == "YES"
    assert rising["daily_buy"] == "missing"

    flat = index_signals(_bars([3, 1, 1, 1, 1, 1]))
    assert flat["above_rising_ma5"] == "NO"

    assert index_signals(_bars([1, 2, 3, 4]))["above_rising_ma5"] == "missing"


def test_weekly_buy_uses_last_session_of_the_week() -> None:
    weekly_yes = [1.0] * 10 + [3.0] * 9 + [4.0]
    assert index_signals(_fridays(weekly_yes))["weekly_buy"] == "YES"

    holiday_week = [
        {"date": "2026-01-05", "close": 10.0},
        {"date": "2026-01-07", "close": 12.0},
    ]
    # One week is not enough for a weekly buy.
    assert index_signals(holiday_week)["weekly_buy"] == "missing"

    short_weeks = _fridays([float(i) for i in range(1, 20)])
    extra_days = _bars([2.0] * 25)
    mixed = extra_days + short_weeks
    mixed.sort(key=lambda bar: bar["date"])
    assert index_signals(mixed)["weekly_buy"] == "missing"
    assert index_signals(mixed)["daily_buy"] in {"YES", "NO"}


def _hand_ma(closes: list[float], window: int) -> float:
    return sum(closes[-window:]) / window


def _checked_signals(bars: list[dict]) -> dict:
    closes = [bar["close"] for bar in bars]
    ma5 = _hand_ma(closes, 5)
    ma10 = _hand_ma(closes, 10)
    ma20 = _hand_ma(closes, 20)
    assert moving_average(closes, 10) == pytest.approx(ma10)
    assert moving_average(closes, 20) == pytest.approx(ma20)
    signals = index_signals(bars)
    last = closes[-1]
    expected_daily = "YES" if last > ma10 and last > ma20 and ma10 > ma20 else "NO"
    expected_ma5 = "YES" if last > ma5 and ma5 > _hand_ma(closes[:-1], 5) else "NO"
    assert signals["daily_buy"] == expected_daily
    assert signals["above_rising_ma5"] == expected_ma5
    assert signals["weekly_buy"] in {"YES", "NO"}
    return {
        "close": round(last, 2),
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "daily_buy": signals["daily_buy"],
        "weekly_buy": signals["weekly_buy"],
        "above_rising_ma5": signals["above_rising_ma5"],
    }


@live
def test_live_ma_matches_hand_calculation_and_golden() -> None:
    paths = {
        "hs300": TDX / "vipdoc" / "sh" / "lday" / "sh000300.day",
        "chinext": TDX / "vipdoc" / "sz" / "lday" / "sz399006.day",
    }
    frozen = json.loads((FIXTURES / "golden_20260923.json").read_text(encoding="utf-8"))
    for name, path in paths.items():
        bars = read_day_bars(path)
        assert isinstance(bars, list)
        _checked_signals(bars)
        as_of = [bar for bar in bars if bar["date"] <= frozen["date"]]
        assert as_of[-1]["date"] == frozen["date"]
        assert frozen[name] == _checked_signals(as_of)
