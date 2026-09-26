"""Daily change boards and RPS boards stay on separate sort keys."""

from __future__ import annotations

import json
import struct
from datetime import date, timedelta
from pathlib import Path

import pytest

from briefing.analysis.ranks import SHORT_LIST, daily_top10, rps_top10
from briefing.tdx.blocks import load_block_maps
from briefing.tdx.extdata import read_extdata_series

TDX = Path(r"C:\zd_pazq_hy")
ON = "2026-09-23"
GOLDEN = Path(__file__).parent / "fixtures" / "golden_ranks_20260924.json"
live = pytest.mark.skipif(not (TDX / "vipdoc" / "sh" / "lday" / "sh000300.day").is_file(), reason="skip")


def _day(path: Path, closes: list[tuple[int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        struct.pack("<IIIIIfII", day, close, close, close, close, 0.0, 100, 0) for day, close in closes
    )
    path.write_bytes(payload)


def _extdata(directory: Path, ext_num: int, series: dict[str, list[tuple[int, float]]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    idx = bytearray()
    dat = bytearray()
    for code, points in series.items():
        record = bytearray(29)
        record[2:8] = code.encode("ascii")
        record[25:29] = len(points).to_bytes(4, "little")
        idx.extend(record)
        for day, value in points:
            dat.extend(struct.pack("<Iff", day, 0.0, value))
    (directory / f"extdata_{ext_num}.idx").write_bytes(idx)
    (directory / f"extdata_{ext_num}.dat").write_bytes(dat)


def test_daily_boards_sort_by_pct_and_stay_separate(tmp_path: Path) -> None:
    lday = tmp_path / "lday"
    _day(lday / "sh880301.day", [(20260922, 10000), (20260923, 11000)])
    _day(lday / "sh880302.day", [(20260922, 10000), (20260923, 9000)])
    _day(lday / "sh880303.day", [(20260922, 10000), (20260923, 10500)])
    _day(lday / "sh880501.day", [(20260922, 10000), (20260923, 12000)])
    _day(lday / "sh880502.day", [(20260922, 10000), (20260923, 8000)])
    groups = {
        "industry": [
            {"code": "880302", "name": "弱"},
            {"code": "880301", "name": "强"},
            {"code": "880303", "name": "中"},
        ],
        "concept": [
            {"code": "880502", "name": "概念弱"},
            {"code": "880501", "name": "概念强"},
        ],
    }
    boards = daily_top10(groups, lday, ON)
    assert [item["name"] for item in boards["industry"]["items"]] == ["强", "中", "弱"]
    assert [item["name"] for item in boards["concept"]["items"]] == ["概念强", "概念弱"]
    assert boards["industry"]["items"][0]["pct"] == pytest.approx(0.1)
    assert "880501" not in {item["code"] for item in boards["industry"]["items"]}


def test_rps_order_ignores_the_opposite_interval_change(tmp_path: Path) -> None:
    lday = tmp_path / "lday"
    # Sixteen bars so a 15-bar lookback has a base. The strong RPS name falls.
    up = [(20260900 + index, 10000 + index * 100) for index in range(1, 16)] + [(20260923, 20000)]
    down = [(20260900 + index, 20000) for index in range(1, 16)] + [(20260923, 10000)]
    _day(lday / "sh880301.day", down)
    _day(lday / "sh880302.day", up)
    extdata = tmp_path / "extdata"
    _extdata(extdata, 12, {"880301": [(20260923, 90.0)], "880302": [(20260923, 10.0)]})
    groups = {
        "industry": [
            {"code": "880302", "name": "涨得多"},
            {"code": "880301", "name": "涨得少"},
        ],
        "concept": [],
    }
    board = rps_top10(groups, lday, extdata, ON)["industry"][15]
    assert [item["name"] for item in board["items"]] == ["涨得少", "涨得多"]
    assert board["items"][0]["rps"] == 90.0
    assert board["items"][0]["pct"] < board["items"][1]["pct"]


def test_style_codes_from_the_block_map_stay_out(tmp_path: Path) -> None:
    tdxzs = tmp_path / "tdxzs.cfg"
    incon = tmp_path / "incon.dat"
    info = tmp_path / "infoharbor_block.dat"
    tdxzs.write_bytes("煤炭|880301|2|1|0|T0101\n轮动趋势|880081|5|2|0|x\n".encode("gbk"))
    incon.write_bytes("T0101|煤炭\n".encode("gbk"))
    info.write_bytes("#GN_人工智能,3,880506,0,0,,\n".encode("gbk"))
    groups = load_block_maps(tdxzs, incon, info)
    lday = tmp_path / "lday"
    for code, close in (("880301", 11000), ("880081", 15000), ("880506", 12000)):
        _day(lday / f"sh{code}.day", [(20260922, 10000), (20260923, close)])
    boards = daily_top10(groups, lday, ON)
    codes = {item["code"] for item in boards["industry"]["items"] + boards["concept"]["items"]}
    assert codes == {"880301", "880506"}
    assert "880081" not in codes


def test_fewer_than_ten_names_is_a_short_list(tmp_path: Path) -> None:
    lday = tmp_path / "lday"
    _day(lday / "sh880301.day", [(20260922, 10000), (20260923, 11000)])
    groups = {"industry": [{"code": "880301", "name": "煤炭"}], "concept": []}
    boards = daily_top10(groups, lday, ON)
    assert boards["industry"]["flag"] == SHORT_LIST
    assert len(boards["industry"]["items"]) == 1
    assert boards["concept"]["flag"] == SHORT_LIST
    assert boards["concept"]["items"] == []


def test_missing_rps_is_skipped_and_missing_change_stays(tmp_path: Path) -> None:
    lday = tmp_path / "lday"
    _day(lday / "sh880301.day", [(20260923, 10000)])
    extdata = tmp_path / "extdata"
    _extdata(
        extdata,
        12,
        {
            "880301": [(20260923, 70.0)],
            "880302": [(20260923, 80.0)],
        },
    )
    groups = {
        "industry": [
            {"code": "880302", "name": "无区间"},
            {"code": "880301", "name": "只有一根"},
            {"code": "880303", "name": "无排名"},
        ],
        "concept": [],
    }
    board = rps_top10(groups, lday, extdata, ON)["industry"][15]
    assert [item["name"] for item in board["items"]] == ["无区间", "只有一根"]
    assert board["items"][0]["pct"] == "missing"
    assert board["items"][1]["pct"] == "missing"
    assert "无排名" not in {item["name"] for item in board["items"]}


def test_an_older_session_uses_that_day_not_the_file_tail(tmp_path: Path) -> None:
    start = date(2026, 1, 1)
    closes = []
    for index in range(60):
        day = int((start + timedelta(days=index)).strftime("%Y%m%d"))
        close = 11000 if index == 19 else 50000 if index == 59 else 10000
        closes.append((day, close))
    on_date = (start + timedelta(days=19)).isoformat()
    lday = tmp_path / "lday"
    _day(lday / "sh880301.day", closes)
    groups = {"industry": [{"code": "880301", "name": "回放"}], "concept": []}
    daily = daily_top10(groups, lday, on_date)["industry"]["items"]
    assert len(daily) == 1
    assert daily[0]["pct"] == pytest.approx(0.1)

    extdata = tmp_path / "extdata"
    _extdata(extdata, 11, {"880301": [(int(on_date.replace("-", "")), 80.0)]})
    board = rps_top10(groups, lday, extdata, on_date)["industry"][5]["items"]
    assert board[0]["pct"] == pytest.approx(11000 / 10000 - 1)
    assert board[0]["pct"] != pytest.approx(50000 / 10000 - 1)


def test_a_name_without_the_target_day_is_left_off_the_daily_board(tmp_path: Path) -> None:
    lday = tmp_path / "lday"
    _day(lday / "sh880301.day", [(20260922, 10000)])
    groups = {"industry": [{"code": "880301", "name": "停在昨天"}], "concept": []}
    board = daily_top10(groups, lday, ON)["industry"]
    assert board["items"] == []
    assert board["flag"] == SHORT_LIST


@live
def test_live_daily_boards_and_fifteen_day_rps_follow_extdata_12() -> None:
    groups = load_block_maps(
        TDX / "T0002" / "hq_cache" / "tdxzs.cfg",
        TDX / "incon.dat",
        TDX / "T0002" / "hq_cache" / "infoharbor_block.dat",
    )
    lday = TDX / "vipdoc" / "sh" / "lday"
    extdata = TDX / "T0002" / "extdata"
    daily = daily_top10(groups, lday, ON)
    assert daily["industry"]["items"]
    assert daily["concept"]["items"]
    board = rps_top10(groups, lday, extdata, ON)["industry"][15]
    assert board["items"]
    filed = [read_extdata_series(extdata, 12, item["code"], ON) for item in board["items"]]
    assert filed == [item["rps"] for item in board["items"]]
    assert filed == sorted(filed, reverse=True)
    codes = {item["code"] for kind in daily for item in daily[kind]["items"]}
    codes.update(item["code"] for item in board["items"])
    assert "880081" not in codes


@live
def test_confirmed_golden_ranks_match_name_and_code_order() -> None:
    if not GOLDEN.is_file():
        pytest.skip("等待人工对照通达信确认")
    frozen = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if not frozen.get("confirmed_by_human"):
        pytest.skip("等待人工对照通达信确认")
    groups = load_block_maps(
        TDX / "T0002" / "hq_cache" / "tdxzs.cfg",
        TDX / "incon.dat",
        TDX / "T0002" / "hq_cache" / "infoharbor_block.dat",
    )
    lday = TDX / "vipdoc" / "sh" / "lday"
    extdata = TDX / "T0002" / "extdata"
    on_date = frozen["date"]
    daily = daily_top10(groups, lday, on_date)
    rps = rps_top10(groups, lday, extdata, on_date)
    boards = {
        "industry_daily": daily["industry"]["items"],
        "concept_daily": daily["concept"]["items"],
        "industry_rps_15": rps["industry"][15]["items"],
        "concept_rps_15": rps["concept"][15]["items"],
    }
    for key, items in boards.items():
        assert [(item["name"], item["code"]) for item in items] == [
            (item["name"], item["code"]) for item in frozen[key]
        ]
