"""60-session 25% counts use the passed trading calendar, not each stock's own bars."""

from __future__ import annotations

from briefing.analysis.breadth import breadth_snapshot, count_move


def _calendar(length: int = 61) -> list[str]:
    return [f"{index:04d}-01-01" for index in range(length)]


def _stock(name: str, closes: dict[str, float], *, volume_today: int = 100, today: str) -> dict:
    bars = []
    for day in sorted(closes):
        volume = volume_today if day == today else 100
        bars.append({"date": day, "close": closes[day], "volume": volume})
    return {"name": name, "bars": bars}


def test_exact_25pct_uses_the_calendar_day_sixty_sessions_back() -> None:
    calendar = _calendar()
    base = calendar[0]
    today = calendar[-1]
    up = _stock("ST示例", {base: 100, calendar[30]: 110, today: 125}, today=today)
    down = _stock("普通", {base: 100, today: 75}, today=today)
    # Has a bar today, but not on the session 60 places earlier.
    skipped = _stock("缺口", {calendar[1]: 100, today: 200}, today=today)
    halted = _stock("停牌", {base: 100, today: 200}, today=today, volume_today=0)
    counted = count_move(
        [up, down, skipped, halted],
        today,
        lookback=60,
        threshold=0.25,
        trading_dates=calendar,
    )
    assert counted == {"up": 1, "down": 1}
    snapshot = breadth_snapshot(
        [up, down, skipped, halted],
        today,
        calendar,
        new_high_net=0,
    )
    assert snapshot["up25"] == 1
    assert snapshot["down25"] == 1
    assert snapshot["diff25"] == 0
    # 4% still uses each stock's own previous bar, so the gapped name counts.
    assert snapshot["up4"] == 2
    assert snapshot["down4"] == 1
