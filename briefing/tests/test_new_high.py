"""新高减新低 comes from Tongdaxin extdata_13, not from a close scan."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from briefing.analysis.breadth import breadth_snapshot
from briefing.tdx.extdata import read_new_high_net

TDX = Path(r"C:\zd_pazq_hy\T0002\extdata")
live = pytest.mark.skipif(not (TDX / "extdata_13.idx").is_file(), reason="skip")


def _write_extdata_13(directory: Path) -> None:
    record = bytearray(29)
    record[0:2] = (1).to_bytes(2, "little")
    record[2:8] = b"000001"
    record[25:29] = (2).to_bytes(4, "little")
    (directory / "extdata_13.idx").write_bytes(record)
    (directory / "extdata_13.dat").write_bytes(
        struct.pack("<If f", 20260923, 0.0, 45.0) + struct.pack("<If f", 20260924, 0.0, -71.0)
    )


def test_new_high_net_is_the_extdata_13_difference(tmp_path: Path) -> None:
    _write_extdata_13(tmp_path)
    assert read_new_high_net(tmp_path, "2026-09-24") == -71
    assert read_new_high_net(tmp_path, "2026-09-23") == 45
    assert read_new_high_net(tmp_path, "2026-09-22") == "missing"


def test_snapshot_keeps_only_the_net_and_still_counts_4pct() -> None:
    snapshot = breadth_snapshot(
        [{"bars": [{"date": "2026-03-01", "close": 100.0, "volume": 100}, {"date": "2026-03-02", "close": 104.0, "volume": 100}]}],
        "2026-03-02",
        ["2026-03-01", "2026-03-02"],
        new_high_net=-71,
    )
    assert snapshot["net"] == -71
    assert "nh" not in snapshot
    assert "nl" not in snapshot
    assert snapshot["up4"] == 1
    assert snapshot["down4"] == 0


def test_missing_net_does_not_block_the_4pct_count() -> None:
    snapshot = breadth_snapshot(
        [{"bars": [{"date": "2026-03-01", "close": 100.0, "volume": 100}, {"date": "2026-03-02", "close": 104.0, "volume": 100}]}],
        "2026-03-02",
        ["2026-03-01", "2026-03-02"],
        new_high_net="missing",
    )
    assert snapshot["net"] == "missing"
    assert snapshot["up4"] == 1


@live
def test_live_extdata_13_on_20260924_is_the_checked_difference() -> None:
    assert read_new_high_net(TDX, "2026-09-24") == -71
