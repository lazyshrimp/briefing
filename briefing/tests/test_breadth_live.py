"""Live breadth on the local Tongdaxin files, checked against an independent recount."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from briefing.analysis.breadth import breadth_snapshot, count_move, ratio_from_counts
from briefing.analysis.ma50 import a_share_denominators, ma50_ratios
from briefing.tdx.day import read_day_bars
from briefing.tdx.extdata import read_market_extdata, read_new_high_net
from briefing.tdx.universe import load_a_share_universe

TDX = Path(r"C:\zd_pazq_hy")
EXT = TDX / "T0002" / "extdata"
INDEX = TDX / "vipdoc" / "sh" / "lday" / "sh000300.day"
GOLDEN = Path(__file__).parent / "fixtures" / "golden_breadth_20260923.json"
live = pytest.mark.skipif(not INDEX.is_file(), reason="skip")


def _write_day(path: Path, rows: list[tuple[int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(struct.pack("<IIIIIfII", day, close, close, close, close, 0.0, volume, 0) for day, close, volume in rows)
    path.write_bytes(payload)


def test_missing_day_file_counts_as_a_failure(tmp_path: Path) -> None:
    quote = tmp_path / "T0002" / "hq_cache" / "specgpext.txt"
    quote.parent.mkdir(parents=True)
    quote.write_bytes("1|600000|浦发\n0|000001|平安\n2|920000|北交\n".encode("gbk"))
    _write_day(tmp_path / "vipdoc" / "sh" / "lday" / "sh600000.day", [(20260923, 1000, 100)])
    universe, failures = load_a_share_universe(tmp_path, "2026-09-23")
    assert failures == 1
    assert [item["code"] for item in universe] == ["600000"]
    assert universe[0]["bars"] == [{"date": "2026-09-23", "close": 10.0, "volume": 100}]


def _flag_from_golden(part: dict) -> dict:
    return ratio_from_counts([part["up"]], [part["down"]])


@live
def test_last_session_identities_and_golden_day() -> None:
    calendar = read_day_bars(INDEX)
    assert isinstance(calendar, list)
    trading_dates = [bar["date"] for bar in calendar]
    last = trading_dates[-1]
    universe, failures = load_a_share_universe(TDX, last)
    net = read_new_high_net(EXT, last)
    snapshot = breadth_snapshot(universe, last, trading_dates, new_high_net=net, read_failures=failures)
    assert "nh" not in snapshot and "nl" not in snapshot
    assert snapshot["diff25"] == snapshot["up25"] - snapshot["down25"]
    for length, key in ((5, "ratio5"), (10, "ratio10")):
        ups = []
        downs = []
        for day in trading_dates[-length:]:
            counted = count_move(universe, day, lookback=1, threshold=0.04)
            ups.append(counted["up"])
            downs.append(counted["down"])
        assert snapshot[key] == ratio_from_counts(ups, downs)

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    day = golden["date"]
    dates = [item for item in trading_dates if item <= day]
    checked = breadth_snapshot(
        universe,
        day,
        dates,
        new_high_net=read_new_high_net(EXT, day),
        read_failures=failures,
    )
    assert checked["net"] == golden["net"]
    assert checked["up4"] == golden["up4"]
    assert checked["down4"] == golden["down4"]
    assert checked["up25"] == golden["up25"]
    assert checked["down25"] == golden["down25"]
    assert checked["diff25"] == golden["diff25"]
    assert checked["ratio5"] == _flag_from_golden(golden["ratio5"])
    assert checked["ratio10"] == _flag_from_golden(golden["ratio10"])

    denoms = a_share_denominators(TDX)
    ratios = ma50_ratios(
        hs300_above=read_market_extdata(EXT, 5, day),
        hs300_total=denoms["hs300"],
        chinext_above=read_market_extdata(EXT, 6, day),
        chinext_total=denoms["chinext"],
        all_a_above=read_market_extdata(EXT, 4, day),
        all_a_total=denoms["all_a"],
    )
    for name in ("hs300", "chinext", "all_a"):
        assert ratios[name]["above"] == golden["ma50"][name]["above"]
        assert ratios[name]["total"] == golden["ma50"][name]["total"]
