"""4% counts and the 5-day and 10-day ratios of those counts."""

from __future__ import annotations

from briefing.analysis.breadth import NO_DOWN_4, BUYERS_DOMINATE, MISSING, breadth_snapshot, ratio_from_counts


def _bars(closes: list[float], volumes: list[int] | None = None) -> list[dict]:
    bars = []
    for index, close in enumerate(closes):
        bars.append(
            {
                "date": f"2026-03-{index + 1:02d}",
                "close": close,
                "volume": 100 if volumes is None else volumes[index],
            }
        )
    return bars


def test_ratio_is_the_quotient_of_the_sums() -> None:
    assert ratio_from_counts([2, 3, 1, 0, 4], [1, 1, 2, 1, 0]) == {
        "value": 10 / 5,
        "flag": BUYERS_DOMINATE,
    }
    assert ratio_from_counts([1, 1], [1, 1]) == {"value": 1.0, "flag": None}


def test_zero_down_sum_is_no_down_4() -> None:
    assert ratio_from_counts([3, 0, 1, 0, 2], [0, 0, 0, 0, 0])["flag"] == NO_DOWN_4


def test_breakout_rules_on_a_small_universe() -> None:
    mover = {
        "name": "ST示例",
        "bars": _bars([100, 104, 104, 90, 90, 100], [100, 100, 100, 100, 0, 100]),
    }
    quiet = {"name": "普通", "bars": _bars([50, 50, 50, 50, 50, 48])}
    dates = [bar["date"] for bar in mover["bars"]]
    on_date = dates[-1]
    snapshot = breadth_snapshot([mover, quiet], on_date, dates, new_high_net=0)

    # Last day: ST 100/90 is up; quiet 48/50 is down. The halted day is not today.
    assert snapshot["up4"] == 1
    assert snapshot["down4"] == 1
    # Last five sessions: mover +4% on day 2, −13.5% on day 4, volume 0 on day 5, +11% on day 6.
    # Quiet is −4% on day 6. Up 2, down 2, so the flag stays empty.
    assert snapshot["ratio5"] == {"value": 1.0, "flag": None}


def test_five_day_ratio_buyers_dominate_at_snapshot_level() -> None:
    stock = {"name": "普通", "bars": _bars([100, 96, 100, 104, 110])}
    dates = [bar["date"] for bar in stock["bars"]]
    snapshot = breadth_snapshot([stock], dates[-1], dates, new_high_net=0)
    assert snapshot["ratio5"] == {"value": 3 / 1, "flag": BUYERS_DOMINATE}


def test_stock_without_a_previous_close_is_not_counted() -> None:
    listed = {"name": "新股", "bars": _bars([10])}
    snapshot = breadth_snapshot([listed], listed["bars"][-1]["date"], ["2026-03-01"], new_high_net=0)
    assert snapshot["up4"] == 0
    assert snapshot["down4"] == 0


def test_every_read_failing_marks_the_4pct_fields_missing() -> None:
    snapshot = breadth_snapshot([], "2026-03-06", [], new_high_net=0, read_failures=3)
    assert snapshot["up4"] == MISSING
    assert snapshot["ratio5"] == MISSING
    assert snapshot["ratio10"] == MISSING
