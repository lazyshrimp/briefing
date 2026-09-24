"""Trading-day checks against an index day file."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from briefing.core.calendar import is_trading_day

TDX = Path(r"C:\zd_pazq_hy")
live = pytest.mark.skipif(not (TDX / "vipdoc" / "sh" / "lday" / "sh000300.day").is_file(), reason="skip")


def _day(date_int: int) -> bytes:
    return struct.pack("<IIIIIfII", date_int, 100, 100, 100, 100, 0.0, 1, 0)


def test_trading_day_skip_and_stop(tmp_path: Path) -> None:
    path = tmp_path / "sh000300.day"
    path.write_bytes(_day(20260918) + _day(20260922))
    assert is_trading_day("2026-09-18", path) == "trading_day"
    assert is_trading_day("2026-09-21", path) == "skip"
    assert is_trading_day("20260922", path) == "trading_day"
    assert is_trading_day("2026-09-18", tmp_path / "missing.day") == "stop"


def test_unreadable_record_length_stops(tmp_path: Path) -> None:
    path = tmp_path / "sh000300.day"
    path.write_bytes(b"\x00" * 7)
    assert is_trading_day("2026-09-18", path) == "stop"


@live
def test_live_calendar_uses_a_real_date_and_a_gap() -> None:
    from briefing.tdx.day import read_day_bars

    path = TDX / "vipdoc" / "sh" / "lday" / "sh000300.day"
    bars = read_day_bars(path)
    assert isinstance(bars, list)
    assert is_trading_day(bars[-1]["date"], path) == "trading_day"

    present = {bar["date"] for bar in bars}
    gap = None
    for bar in bars:
        year, month, day = (int(part) for part in bar["date"].split("-"))
        if day >= 28:
            continue
        candidate = f"{year:04d}-{month:02d}-{day + 1:02d}"
        if candidate not in present:
            gap = candidate
            break
    assert gap is not None
    assert is_trading_day(gap, path) == "skip"
    if "2026-09-20" not in present:
        assert is_trading_day("2026-09-20", path) == "skip"
