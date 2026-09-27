"""Run one day's briefing from the calendar through the evaluator.

D1 through D5 stay in memory. The markdown is written once, at D6, and only
after commentary is present or marked missing. A later failure does not call
the diagnostic path; that path is outside this run.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from briefing.analysis.ma50 import a_share_denominators
from briefing.core.calendar import is_trading_day
from briefing.core.models import Draft, Snapshot
from briefing.evaluation.evaluator import commentary_rejection, evaluate_briefing
from briefing.report.commentary import write_commentary
from briefing.report.sentiment import render_sentiment_chart
from briefing.report.writer import assemble_draft, write_briefing
from briefing.skills.compute_snapshot import compute_snapshot
from briefing.tdx.blocks import load_block_maps
from briefing.tdx.day import read_day_bars, to_date_str
from briefing.tdx.extdata import read_market_extdata, read_new_high_net
from briefing.tdx.universe import load_a_share_universe

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
STOP = "STOP"
_STOP_MARK = "stop"
_SKIP_MARK = "skip"
_TRADING_DAY = "trading_day"
_DEFAULT_TDX = Path(r"C:\zd_pazq_hy")


def run_daily(
    on_date: str,
    *,
    tdx_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    sentiment_csv: str | Path | None = None,
    chart_png: str | Path | None = None,
    complete=None,
    progress=None,
) -> dict:
    """Run D1 through D7 for one date. Return the path and the evaluator result."""
    on_date = to_date_str(on_date)
    root = Path(tdx_dir) if tdx_dir is not None else _DEFAULT_TDX
    output = Path(output_dir) if output_dir is not None else _default_output()
    csv_path = Path(sentiment_csv) if sentiment_csv is not None else _default_csv()
    png_path = Path(chart_png) if chart_png is not None else _default_png()
    steps: list[str] = []

    steps.append("D1")
    _note(progress, "D1 核对是不是交易日")
    calendar = d1_calendar(on_date, root)
    if str(calendar).lower() == _SKIP_MARK:
        _note(progress, "这一天不是交易日，不生成简报")
        return _result(SKIP, steps=steps)
    if str(calendar).lower() != _TRADING_DAY:
        _note(progress, "交易日判断停住了，没有写出简报")
        return _result(STOP, steps=steps)

    steps.append("D2")
    _note(progress, "D2 读取通达信行情。全市场扫描大约一两分钟")
    raw = d2_read(on_date, root)
    if _stopped(raw):
        _note(progress, "行情没有读到目标日，停止")
        return _result(STOP, steps=steps)

    steps.append("D3")
    _note(progress, "D3 计算信号、广度和榜单")
    snapshot = d3_compute(raw)
    if _stopped(snapshot):
        _note(progress, "计算停住了，停止")
        return _result(STOP, steps=steps)

    steps.append("D4")
    _note(progress, "D4 读取情绪数据")
    loaded = d4_sentiment(csv_path, png_path, root)
    if _stopped(loaded):
        _note(progress, "情绪数据停住了，停止")
        return _result(STOP, steps=steps)

    draft = assemble_draft(
        on_date,
        snapshot.signals,
        snapshot.breadth,
        snapshot.ma50,
        snapshot.ranks,
        loaded["sentiment"],
    )
    steps.append("D5")
    _note(progress, "D5 写市场评论")
    d5_commentary(draft, complete=complete)

    steps.append("D6")
    _note(progress, "D6 写入简报文件")
    written = d6_write(draft, output)
    if _stopped(written):
        _note(progress, "写入失败，停止")
        return _result(STOP, steps=steps)

    context = _context(on_date, output, csv_path, root, draft, loaded)
    steps.append("D7")
    _note(progress, "D7 按行情再核一遍。这一步会再扫一次全市场，大约一两分钟")
    evaluation = d7_evaluate(written["path"], draft, context)
    status = str(evaluation.get("status", STOP))
    if status not in {PASS, FAIL, STOP}:
        status = STOP
    return _result(status, path=written["path"], evaluation=evaluation, steps=steps)


def d1_calendar(on_date: str, tdx_dir: Path) -> str:
    """Trading day, skip, or stop.

    A date inside the index history with no bar is skip. A target later than
    the last bar means the day file has not been updated, which is stop.
    """
    root = Path(tdx_dir)
    index = _index_path(root)
    if not root.is_dir():
        return _STOP_MARK
    status = is_trading_day(on_date, index)
    if status == _STOP_MARK:
        return _STOP_MARK
    if status == _TRADING_DAY:
        return _TRADING_DAY
    bars = read_day_bars(index)
    if isinstance(bars, list) and bars and bars[-1]["date"] < on_date:
        return _STOP_MARK
    return _SKIP_MARK


def d2_read(on_date: str, tdx_dir: Path) -> dict | str:
    """Load the raw records D3 consumes. One missing series stays missing."""
    root = Path(tdx_dir)
    if not root.is_dir():
        return _STOP_MARK
    hs300 = _through(_index_path(root), on_date)
    if hs300 is None:
        return _STOP_MARK
    chinext = _through(root / "vipdoc" / "sz" / "lday" / "sz399006.day", on_date)
    universe, failures = load_a_share_universe(root, on_date)
    extdata = root / "T0002" / "extdata"
    groups = load_block_maps(
        root / "T0002" / "hq_cache" / "tdxzs.cfg",
        root / "incon.dat",
        root / "T0002" / "hq_cache" / "infoharbor_block.dat",
    )
    return {
        "on_date": on_date,
        "hs300_bars": hs300,
        "chinext_bars": chinext if chinext is not None else "missing",
        "trading_dates": [bar["date"] for bar in hs300],
        "universe": universe,
        "read_failures": failures,
        "new_high_net": read_new_high_net(extdata, on_date),
        "hs300_above": read_market_extdata(extdata, 5, on_date),
        "chinext_above": read_market_extdata(extdata, 6, on_date),
        "all_a_above": read_market_extdata(extdata, 4, on_date),
        "denominators": a_share_denominators(root),
        "groups": groups,
        "lday_dir": root / "vipdoc" / "sh" / "lday",
        "extdata_dir": extdata,
    }


def d3_compute(raw: dict) -> Snapshot | str:
    return compute_snapshot(raw)


def d4_sentiment(csv_path: Path, png_path: Path, tdx_dir: Path) -> dict | str:
    """Reuse the last stored week. This run does not append a new vote."""
    rows = _sentiment_rows(Path(csv_path))
    if not rows:
        return {
            "sentiment": "missing",
            "chart_redrawn": False,
            "new_sentiment_week": False,
            "chart_points": 0,
        }
    before = _digest(png_path)
    chart = render_sentiment_chart(csv_path, png_path, tdx_dir)
    after = _digest(png_path)
    last = rows[-1]
    if isinstance(chart, dict):
        chart_path = str(chart["path"])
        points = chart["points"]
    else:
        chart_path = "missing"
        points = 0
    return {
        "sentiment": {
            "date": last["date"],
            "bull": float(last["bull"]),
            "bear": float(last["bear"]),
            "flat": float(last["flat"]),
            "spread": float(last["spread"]),
            "chart": chart_path,
        },
        "chart_redrawn": before is not None and after != before,
        "new_sentiment_week": False,
        "chart_points": points,
    }


def d5_commentary(draft: Draft, complete=None):
    """Write commentary from the draft. Check 8 can reject it once."""
    snapshot = _snapshot_dict(draft)

    def judge(text: str, metrics_used: list[str]) -> str | None:
        return commentary_rejection(text, metrics_used, snapshot)

    return write_commentary(draft, complete=complete, judge=judge)


def d6_write(draft: Draft, output_dir: Path) -> dict | str:
    """Write the day's markdown once. The writer refuses an empty commentary slot."""
    return write_briefing(draft, output_dir)


def d7_evaluate(path: str, draft: Draft, context: dict) -> dict:
    """Judge the file that D6 just wrote. Reference is recomputed independently."""
    return evaluate_briefing(path, _snapshot_dict(draft), None, context=context)


def _context(on_date: str, output: Path, csv_path: Path, tdx_dir: Path, draft: Draft, loaded: dict) -> dict:
    metrics = []
    if draft.commentary is not None:
        metrics = list(draft.commentary.metrics_used)
    return {
        "on_date": on_date,
        "is_trading_day": _TRADING_DAY,
        "output_dir": str(output),
        "sentiment_csv": str(csv_path),
        "chart_redrawn": bool(loaded.get("chart_redrawn")),
        "new_sentiment_week": bool(loaded.get("new_sentiment_week")),
        "chart_points": loaded.get("chart_points"),
        "metrics_used": metrics,
        "tdx_dir": str(tdx_dir),
    }


def _snapshot_dict(draft: Draft) -> dict:
    return {
        "signals": draft.snapshot.signals,
        "breadth": draft.snapshot.breadth,
        "ma50": draft.snapshot.ma50,
        "ranks": draft.snapshot.ranks,
        "sentiment": draft.sentiment,
    }


def _through(path: Path, on_date: str) -> list[dict] | None:
    bars = read_day_bars(path)
    if not isinstance(bars, list):
        return None
    kept = [bar for bar in bars if bar["date"] <= on_date]
    if not kept or kept[-1]["date"] != on_date:
        return None
    return kept


def _index_path(root: Path) -> Path:
    return root / "vipdoc" / "sh" / "lday" / "sh000300.day"


def _sentiment_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _note(progress, message: str) -> None:
    if progress is not None:
        progress(message)


def _stopped(value: object) -> bool:
    return isinstance(value, str) and value.lower() == _STOP_MARK


def _result(status: str, *, path: str | None = None, evaluation: dict | None = None, steps: list[str]) -> dict:
    return {
        "status": status,
        "path": path,
        "evaluation": evaluation,
        "completed": status == PASS,
        "candidate": status == FAIL and path is not None,
        "steps": steps,
    }


def _default_output() -> Path:
    return Path(__file__).resolve().parents[1] / "output"


def _default_csv() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "sentiment.csv"


def _default_png() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "sentiment.png"
