"""Readers for Tongdaxin day, extdata, and block-name files."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from briefing.tdx.blocks import load_block_maps
from briefing.tdx.day import read_day_bars
from briefing.tdx.extdata import read_extdata_series

TDX = Path(r"C:\zd_pazq_hy")
live = pytest.mark.skipif(not TDX.is_dir(), reason="skip")


def _pack_day(date_int: int, close_fen: int) -> bytes:
    return struct.pack("<IIIIIfII", date_int, close_fen, close_fen, close_fen, close_fen, 0.0, 100, 0)


def test_day_bars_ascending_and_price_scale(tmp_path: Path) -> None:
    path = tmp_path / "sh000300.day"
    path.write_bytes(_pack_day(20260918, 432150) + _pack_day(20260922, 430000))
    bars = read_day_bars(path)
    assert bars == [
        {"date": "2026-09-18", "close": 4321.50},
        {"date": "2026-09-22", "close": 4300.00},
    ]
    assert read_day_bars(path, last_n=1) == [{"date": "2026-09-22", "close": 4300.00}]


def test_day_bars_missing_on_bad_length(tmp_path: Path) -> None:
    path = tmp_path / "broken.day"
    path.write_bytes(b"\x00" * 10)
    assert read_day_bars(path) == "missing"
    assert read_day_bars(tmp_path / "absent.day") == "missing"


def test_day_bars_reject_dates_that_go_backwards(tmp_path: Path) -> None:
    path = tmp_path / "back.day"
    path.write_bytes(_pack_day(20260922, 100) + _pack_day(20260918, 100))
    assert read_day_bars(path) == "missing"


def _write_extdata(directory: Path) -> None:
    code_a = b"000001"
    code_b = b"880301"
    idx = bytearray()
    for code, count in ((code_a, 1), (code_b, 2)):
        record = bytearray(29)
        record[0:2] = (0).to_bytes(2, "little")
        record[2:8] = code
        record[25:29] = count.to_bytes(4, "little")
        idx.extend(record)
    (directory / "extdata_12.idx").write_bytes(idx)
    dat = b"".join(
        [
            struct.pack("<If f", 20260918, 0.0, 10.0),
            struct.pack("<If f", 20260918, 0.0, 0.0),
            struct.pack("<If f", 20260922, 0.0, 88.5),
        ]
    )
    (directory / "extdata_12.dat").write_bytes(dat)


def test_extdata_value_zero_and_missing(tmp_path: Path) -> None:
    _write_extdata(tmp_path)
    assert read_extdata_series(tmp_path, 12, "880301", "2026-09-22") == pytest.approx(88.5)
    assert read_extdata_series(tmp_path, 12, "880301", "2026-09-18") == 0.0
    assert read_extdata_series(tmp_path, 12, "880999", "2026-09-22") == "missing"
    assert read_extdata_series(tmp_path, 12, "880301", "2026-09-23") == "missing"
    assert read_extdata_series(tmp_path / "nope", 12, "880301", "2026-09-22") == "missing"


def test_block_maps_keep_industry_chain_and_gn_only(tmp_path: Path) -> None:
    tdxzs = tmp_path / "tdxzs.cfg"
    incon = tmp_path / "incon.dat"
    info = tmp_path / "infoharbor_block.dat"
    tdxzs.write_bytes(
        "煤炭|880301|2|1|0|T0101\n轮动趋势|880081|5|2|0|x\n黑龙江|880201|3|1|0|1\n".encode("gbk")
    )
    incon.write_bytes("T0101|煤炭\nT0102|电力\n".encode("gbk"))
    info.write_bytes(
        "#GN_人工智能,3,880506,0,0,,\n#FG_高分红,1,880526,0,0,,\n".encode("gbk")
    )
    loaded = load_block_maps(tdxzs, incon, info)
    assert loaded["industry"] == [{"code": "880301", "name": "煤炭"}]
    assert loaded["concept"] == [{"code": "880506", "name": "人工智能"}]
    codes = {item["code"] for item in loaded["industry"] + loaded["concept"]}
    assert "880081" not in codes
    assert "880201" not in codes
    assert "880526" not in codes


def test_block_maps_stop_when_a_file_is_missing(tmp_path: Path) -> None:
    present = tmp_path / "tdxzs.cfg"
    present.write_text("煤炭|880301", encoding="gbk")
    assert load_block_maps(present, tmp_path / "incon.dat", tmp_path / "info.dat") == "stop"


@live
def test_live_index_closes_extdata_and_block_names() -> None:
    hs300 = read_day_bars(TDX / "vipdoc" / "sh" / "lday" / "sh000300.day")
    chinext = read_day_bars(TDX / "vipdoc" / "sz" / "lday" / "sz399006.day")
    assert isinstance(hs300, list) and isinstance(chinext, list)
    assert [bar["date"] for bar in hs300] == sorted(bar["date"] for bar in hs300)
    assert hs300[-1]["close"] > 0
    assert chinext[-1]["close"] > 0

    target = hs300[-1]["date"]
    extdata_dir = TDX / "T0002" / "extdata"
    idx = (extdata_dir / "extdata_12.idx").read_bytes()
    code = ""
    for index in range(len(idx) // 29):
        raw = idx[index * 29 + 2 : index * 29 + 8].rstrip(b"\x00").decode("ascii", errors="replace")
        if raw.startswith("880"):
            code = raw
            break
    assert code
    value = read_extdata_series(extdata_dir, 12, code, target)
    if value == "missing":
        value = read_extdata_series(extdata_dir, 12, code, hs300[-2]["date"])
    assert isinstance(value, float)

    loaded = load_block_maps(
        TDX / "T0002" / "hq_cache" / "tdxzs.cfg",
        TDX / "incon.dat",
        TDX / "T0002" / "hq_cache" / "infoharbor_block.dat",
    )
    assert loaded["industry"]
    assert loaded["concept"]
    codes = {item["code"] for item in loaded["industry"] + loaded["concept"]}
    assert "880081" not in codes
    assert "880201" not in codes
