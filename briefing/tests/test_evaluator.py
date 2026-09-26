"""Evaluator checks use a handwritten reference, except the live Tongdaxin run."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from briefing.core.models import Commentary
from briefing.evaluation.evaluator import evaluate_briefing
from briefing.report.writer import assemble_draft, write_briefing

ON = "2026-09-24"
TDX = Path(r"C:\zd_pazq_hy")
live = pytest.mark.skipif(not (TDX / "vipdoc" / "sh" / "lday" / "sh000300.day").is_file(), reason="skip")


def _board(items: list[dict]) -> dict:
    return {"items": items}


def _case(tmp_path: Path) -> tuple[Path, dict, dict, dict]:
    png = tmp_path / "charts" / "sentiment.png"
    png.parent.mkdir()
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    csv_path = tmp_path / "sentiment.csv"
    csv_path.write_text(
        "date,bull,bear,flat,spread\n"
        "2023-09-26,40,30,30,10\n"
        "2026-09-19,40,30,30,10\n"
        "2026-09-26,33,42,25,-9\n",
        encoding="utf-8",
    )
    signals = {
        "hs300": {"daily_buy": "YES", "weekly_buy": "YES", "above_rising_ma5": "YES"},
        "chinext": {"daily_buy": "NO", "weekly_buy": "YES", "above_rising_ma5": "NO"},
    }
    breadth = {
        "net": 7,
        "up4": 8,
        "down4": 2,
        "ratio5": {"value": 2.0, "flag": "buyers_dominate"},
        "ratio10": {"value": None, "flag": "no_down_4"},
        "up25": 5,
        "down25": 2,
        "diff25": 3,
    }
    ma50 = {
        "hs300": {"above": 1, "total": 4, "pct": 0.25},
        "chinext": {"above": 1, "total": 2, "pct": 0.5},
        "all_a": {"above": 1, "total": 8, "pct": 0.125},
    }
    ranks = {
        "daily": {
            "industry": _board(
                [
                    {"name": "甲", "code": "880001", "pct": 0.1},
                    {"name": "乙", "code": "880002", "pct": 0.05},
                ]
            ),
            "concept": _board([{"name": "丙", "code": "880501", "pct": 0.01}]),
        },
        "rps": {
            "industry": {period: _board([{"name": "甲", "code": "880001", "pct": 0.02, "rps": 90}]) for period in (5, 10, 15, 20)},
            "concept": {period: _board([{"name": "丙", "code": "880501", "pct": 0.03, "rps": 80}]) for period in (5, 10, 15, 20)},
        },
    }
    sentiment = {
        "date": "2026-09-18",
        "bull": 33.0,
        "bear": 42.0,
        "flat": 25.0,
        "spread": -9.0,
        "chart": str(png),
    }
    draft = assemble_draft(ON, signals, breadth, ma50, ranks, sentiment)
    draft.commentary = Commentary(text="评论桩", metrics_used=["net"])
    output = tmp_path / "output"
    write_briefing(draft, output)
    snapshot = {"signals": signals, "breadth": breadth, "ma50": ma50, "ranks": ranks, "sentiment": sentiment}
    reference = {
        "signals": signals,
        "ma50": ma50,
        "up4": 8,
        "down4": 2,
        "ratio5": {"up": 4, "down": 2},
        "ratio10": {"up": 0, "down": 0},
        "up25": 5,
        "down25": 2,
        "ranks": {
            "daily": {
                "industry": [{"code": "880001", "pct": 0.1}, {"code": "880002", "pct": 0.05}],
                "concept": [{"code": "880501", "pct": 0.01}],
            },
            "rps": {
                "industry": {period: [{"code": "880001", "rps": 90, "pct": 0.02}] for period in (5, 10, 15, 20)},
                "concept": {period: [{"code": "880501", "rps": 80, "pct": 0.03}] for period in (5, 10, 15, 20)},
            },
        },
    }
    context = {
        "on_date": ON,
        "is_trading_day": "trading_day",
        "output_dir": str(output),
        "sentiment_csv": str(csv_path),
        "chart_redrawn": False,
        "new_sentiment_week": False,
        "chart_points": 2,
    }
    return output / f"{ON}.md", snapshot, reference, context


def _run(path: Path, snapshot: dict, reference: dict, context: dict) -> dict:
    return evaluate_briefing(path, snapshot, reference, context=context)


def test_a_matching_briefing_leaves_only_check_8_unchecked(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _run(path, snapshot, reference, context)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert result["requirement_failures"] == []
    assert result["sanity_failures"] == []
    assert result["not_checked"] == [8]
    assert result["status"] != "PASS"


def test_a_wrong_five_day_ratio_is_check_5(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("2.00 买盘占优", "3.00 买盘占优"), encoding="utf-8")
    result = _run(path, snapshot, reference, context)
    assert 5 in result["requirement_failures"]


def test_a_wrong_ma50_denominator_is_check_3(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("25.00%（1 / 4）", "25.00%（1 / 5）"), encoding="utf-8")
    result = _run(path, snapshot, reference, context)
    assert 3 in result["requirement_failures"]


def test_a_swapped_industry_board_is_check_9(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    text = path.read_text(encoding="utf-8")
    text = text.replace("1. 甲 10.00%\n2. 乙 5.00%", "1. 乙 5.00%\n2. 甲 10.00%")
    path.write_text(text, encoding="utf-8")
    result = _run(path, snapshot, reference, context)
    assert 9 in result["requirement_failures"]


def test_a_present_signal_written_as_missing_is_check_11(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "### 沪深300\n\n- Daily Buy Signal：YES",
        "### 沪深300\n\n- Daily Buy Signal：缺失",
        1,
    )
    path.write_text(text, encoding="utf-8")
    result = _run(path, snapshot, reference, context)
    assert 11 in result["requirement_failures"]
    assert 2 not in result["requirement_failures"]


def test_redrawing_without_a_new_week_is_check_7(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    context["chart_redrawn"] = True
    context["new_sentiment_week"] = False
    result = _run(path, snapshot, reference, context)
    assert 7 in result["requirement_failures"]


def test_a_file_on_a_non_trading_day_is_check_1(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    context["is_trading_day"] = "skip"
    result = _run(path, snapshot, reference, context)
    assert 1 in result["requirement_failures"]


def test_a_broken_internal_diff_is_not_requirement_12(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    snapshot["breadth"]["diff25"] = 0
    result = _run(path, snapshot, reference, context)
    assert "internal_identity" in result["sanity_failures"]
    assert 12 not in result["requirement_failures"]
    assert all(isinstance(number, int) and 1 <= number <= 11 for number in result["requirement_failures"])


def _rewrite(snapshot: dict, output: Path) -> Path:
    draft = assemble_draft(
        ON,
        snapshot["signals"],
        snapshot["breadth"],
        snapshot["ma50"],
        snapshot["ranks"],
        snapshot["sentiment"],
    )
    draft.commentary = Commentary(text="评论桩", metrics_used=["net"])
    write_briefing(draft, output)
    return output / f"{ON}.md"


def test_a_recomputed_value_printed_as_missing_is_check_11_only(tmp_path: Path) -> None:
    _path, snapshot, reference, context = _case(tmp_path)
    snapshot["signals"] = {
        index: {field: "missing" for field, _label in (("daily_buy", ""), ("weekly_buy", ""), ("above_rising_ma5", ""))}
        for index in ("hs300", "chinext")
    }
    snapshot["breadth"] = {
        key: "missing" for key in ("net", "up4", "down4", "ratio5", "ratio10", "up25", "down25", "diff25")
    }
    snapshot["ma50"] = {key: "missing" for key in ("hs300", "chinext", "all_a")}
    output = tmp_path / "hidden"
    path = _rewrite(snapshot, output)
    context["output_dir"] = str(output)
    result = _run(path, snapshot, reference, context)
    assert 11 in result["requirement_failures"]
    assert result["details"][11].startswith("复算有值，简报写成了缺失：")
    for number in (2, 3, 4, 5, 6):
        assert number not in result["requirement_failures"]


def test_a_missing_ratio_line_is_check_11_and_not_check_5(tmp_path: Path) -> None:
    _path, snapshot, reference, context = _case(tmp_path)
    snapshot["breadth"]["ratio5"] = "missing"
    output = tmp_path / "ratio"
    path = _rewrite(snapshot, output)
    context["output_dir"] = str(output)
    result = _run(path, snapshot, reference, context)
    assert 11 in result["requirement_failures"]
    assert 5 not in result["requirement_failures"]
    assert result["details"][11].startswith("复算有值，简报写成了缺失：")


def test_an_empty_tdx_directory_returns_stop(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = evaluate_briefing(
        "x.md",
        {},
        None,
        context={"tdx_dir": str(empty), "on_date": "2000-01-04"},
    )
    assert result["status"] == "STOP"
    assert "RecomputeError" in result["details"]["evaluator_error"]


def test_a_recompute_exception_returns_stop(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("recompute failed")

    monkeypatch.setattr("briefing.evaluation.recompute.build_reference", boom)
    result = evaluate_briefing(
        Path("missing.md"),
        {},
        None,
        context={"tdx_dir": "unused", "on_date": ON},
    )
    assert result["status"] == "STOP"
    assert result["requirement_failures"] == []
    assert "RuntimeError" in result["details"]["evaluator_error"]


def test_recompute_source_does_not_import_the_code_under_test() -> None:
    source = Path(__file__).resolve().parents[1].joinpath("evaluation", "recompute.py").read_text(encoding="utf-8")
    assert "briefing.analysis" not in source
    assert "briefing.tdx" not in source


@live
def test_live_20260924_matches_the_independent_reference(tmp_path: Path) -> None:
    import csv

    from briefing.analysis.breadth import breadth_snapshot
    from briefing.analysis.ma50 import a_share_denominators, ma50_ratios
    from briefing.analysis.ranks import daily_top10, rps_top10
    from briefing.analysis.signals import index_signals
    from briefing.evaluation.recompute import build_reference
    from briefing.report.sentiment import render_sentiment_chart
    from briefing.tdx.blocks import load_block_maps
    from briefing.tdx.day import read_day_bars
    from briefing.tdx.extdata import read_market_extdata, read_new_high_net
    from briefing.tdx.universe import load_a_share_universe

    def through(path: Path) -> list[dict]:
        bars = read_day_bars(path)
        kept = [bar for bar in bars if bar["date"] <= ON]
        assert kept[-1]["date"] == ON
        return kept

    signals = {
        "hs300": index_signals(through(TDX / "vipdoc" / "sh" / "lday" / "sh000300.day")),
        "chinext": index_signals(through(TDX / "vipdoc" / "sz" / "lday" / "sz399006.day")),
    }
    calendar = through(TDX / "vipdoc" / "sh" / "lday" / "sh000300.day")
    trading_dates = [bar["date"] for bar in calendar]
    universe, failures = load_a_share_universe(TDX, ON)
    breadth = breadth_snapshot(
        universe,
        ON,
        trading_dates,
        new_high_net=read_new_high_net(TDX / "T0002" / "extdata", ON),
        read_failures=failures,
    )
    denoms = a_share_denominators(TDX)
    extdata = TDX / "T0002" / "extdata"
    ma50 = ma50_ratios(
        hs300_above=read_market_extdata(extdata, 5, ON),
        hs300_total=denoms["hs300"],
        chinext_above=read_market_extdata(extdata, 6, ON),
        chinext_total=denoms["chinext"],
        all_a_above=read_market_extdata(extdata, 4, ON),
        all_a_total=denoms["all_a"],
    )
    groups = load_block_maps(
        TDX / "T0002" / "hq_cache" / "tdxzs.cfg",
        TDX / "incon.dat",
        TDX / "T0002" / "hq_cache" / "infoharbor_block.dat",
    )
    lday = TDX / "vipdoc" / "sh" / "lday"
    ranks = {"daily": daily_top10(groups, lday, ON), "rps": rps_top10(groups, lday, extdata, ON)}
    csv_path = Path(__file__).resolve().parents[1] / "data" / "sentiment.csv"
    stored_png = csv_path.with_name("sentiment.png")
    before = hashlib.sha256(stored_png.read_bytes()).hexdigest()
    with csv_path.open(encoding="utf-8", newline="") as handle:
        last = list(csv.DictReader(handle))[-1]
    chart_png = tmp_path / "sentiment.png"
    chart = render_sentiment_chart(csv_path, chart_png, TDX)
    sentiment = {
        "date": last["date"],
        "bull": float(last["bull"]),
        "bear": float(last["bear"]),
        "flat": float(last["flat"]),
        "spread": float(last["spread"]),
        "chart": str(chart_png),
    }
    draft = assemble_draft(ON, signals, breadth, ma50, ranks, sentiment)
    draft.commentary = Commentary(text="评论桩", metrics_used=["net"])
    output = tmp_path / "output"
    write_briefing(draft, output)
    reference = build_reference(TDX, ON)
    result = evaluate_briefing(
        output / f"{ON}.md",
        {"signals": signals, "breadth": breadth, "ma50": ma50, "ranks": ranks, "sentiment": sentiment},
        reference,
        context={
            "on_date": ON,
            "is_trading_day": "trading_day",
            "output_dir": str(output),
            "sentiment_csv": str(csv_path),
            "chart_redrawn": False,
            "new_sentiment_week": False,
            "chart_points": chart["points"],
        },
    )
    assert result["requirement_failures"] == []
    assert result["sanity_failures"] == []
    assert result["not_checked"] == [8]
    assert hashlib.sha256(stored_png.read_bytes()).hexdigest() == before
