"""Assemble an in-memory draft and write it once commentary is present.

The five headings are the blocks in requirement section 3. A missing value
is written as 缺失. The day's file is published by renaming a temporary
file, and only after the commentary slot is filled or marked missing.
"""

from __future__ import annotations

import os
from pathlib import Path

from briefing.analysis.breadth import BUYERS_DOMINATE, NO_DOWN_4
from briefing.analysis.ranks import SHORT_LIST
from briefing.core.models import Commentary, Draft, Snapshot

STOP = "stop"
MISSING = "missing"
SECTIONS = (
    "市场趋势",
    "广度",
    "投资者情绪",
    "市场评论",
    "板块与概念",
)
_INDEXES = (("hs300", "沪深300"), ("chinext", "创业板指"))
_SIGNALS = (
    ("daily_buy", "Daily Buy Signal"),
    ("weekly_buy", "Weekly Buy Signal"),
    ("above_rising_ma5", "Price Action Above Rising 5-DMA"),
)
_RANK_PERIODS = (("当日", None), ("5日", 5), ("10日", 10), ("15日", 15), ("20日", 20))
_KINDS = (("industry", "行业"), ("concept", "概念"))


def assemble_draft(
    on_date: str,
    signals: dict,
    breadth: dict,
    ma50: dict,
    ranks: dict,
    sentiment: dict | str,
) -> Draft:
    """Build a draft whose commentary slot is still empty."""
    return Draft(
        snapshot=Snapshot(
            on_date=on_date,
            signals=signals,
            breadth=breadth,
            ma50=ma50,
            ranks=ranks,
        ),
        sentiment=sentiment,
        commentary=None,
    )


def write_briefing(draft: Draft, output_dir: str | Path | None = None) -> dict | str:
    """Write ``YYYY-MM-DD.md`` after D5. An empty commentary slot writes nothing."""
    if not _commentary_ready(draft.commentary):
        return STOP
    on_date = draft.snapshot.on_date
    if len(on_date) != 10 or on_date[4] != "-" or on_date[7] != "-":
        return STOP
    directory = Path(output_dir) if output_dir is not None else _default_output()
    target = directory / f"{on_date}.md"
    temporary = directory / f".{on_date}.md.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(_render(draft, directory), encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    except OSError:
        temporary.unlink(missing_ok=True)
        return STOP
    return {"path": str(target)}


def _default_output() -> Path:
    return Path(__file__).resolve().parents[1] / "output"


def _commentary_ready(commentary: Commentary | None) -> bool:
    if commentary is None or not isinstance(commentary, Commentary):
        return False
    if commentary.is_missing():
        return True
    return bool(commentary.text.strip())


def _is_missing(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() == MISSING


def _show(value: object) -> str:
    if value is None or _is_missing(value):
        return "缺失"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _render(draft: Draft, markdown_dir: Path) -> str:
    commentary = draft.commentary
    assert commentary is not None
    blocks = [
        _signals_block(draft.snapshot.signals),
        _breadth_block(draft.snapshot.breadth, draft.snapshot.ma50),
        _sentiment_block(draft.sentiment, markdown_dir),
        _commentary_block(commentary),
        _ranks_block(draft.snapshot.ranks),
    ]
    lines = [f"# {draft.snapshot.on_date}", ""]
    for title, body in zip(SECTIONS, blocks, strict=True):
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _signals_block(signals: dict | str) -> list[str]:
    if _is_missing(signals) or not isinstance(signals, dict):
        return ["缺失"]
    lines: list[str] = []
    for key, label in _INDEXES:
        lines.append(f"### {label}")
        lines.append("")
        index = signals.get(key)
        if _is_missing(index) or not isinstance(index, dict):
            lines.append("缺失")
            lines.append("")
            continue
        for field, name in _SIGNALS:
            lines.append(f"- {name}：{_show(index.get(field))}")
        lines.append("")
    return lines


def _breadth_block(breadth: dict | str, ma50: dict | str) -> list[str]:
    if _is_missing(breadth) or not isinstance(breadth, dict):
        breadth = {}
    lines = [f"- 52周新高减新低：{_show(breadth.get('net'))}"]
    lines.extend(_ma50_lines(ma50))
    lines.append(f"- 当日4%+涨/跌家数：{_pair(breadth.get('up4'), breadth.get('down4'))}")
    lines.append(f"- 4%突破比率（5日）：{_ratio(breadth.get('ratio5'))}")
    lines.append(f"- 4%突破比率（10日）：{_ratio(breadth.get('ratio10'))}")
    lines.append(f"- 滚动60日涨/跌25%家数：{_pair(breadth.get('up25'), breadth.get('down25'))}")
    lines.append(f"- 60日25%多空差：{_show(breadth.get('diff25'))}")
    return lines


def _ma50_lines(ma50: dict | str) -> list[str]:
    labels = (
        ("hs300", "沪深300 50日线以上比例"),
        ("chinext", "创业板 50日线以上比例"),
        ("all_a", "沪深 50日线以上比例"),
    )
    if _is_missing(ma50) or not isinstance(ma50, dict):
        return [f"- {label}：缺失" for _, label in labels]
    lines = []
    for key, label in labels:
        lines.append(f"- {label}：{_fraction(ma50.get(key))}")
    return lines


def _pair(up: object, down: object) -> str:
    if _is_missing(up) or _is_missing(down) or up is None or down is None:
        return "缺失"
    return f"{_show(up)} / {_show(down)}"


def _fraction(item: object) -> str:
    if _is_missing(item) or not isinstance(item, dict):
        return "缺失"
    above = _number(item.get("above"))
    total = _number(item.get("total"))
    if above is None or total is None or total <= 0:
        return "缺失"
    percent = above / total * 100
    return f"{percent:.2f}%（{_show(item.get('above'))} / {_show(item.get('total'))}）"


def _number(value: object) -> float | None:
    if value is None or _is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _ratio(item: object) -> str:
    if _is_missing(item) or not isinstance(item, dict):
        return "缺失"
    if item.get("flag") == NO_DOWN_4:
        return "无跌幅≥4%"
    value = item.get("value")
    if value is None or _is_missing(value):
        return "缺失"
    text = f"{float(value):.2f}"
    if item.get("flag") == BUYERS_DOMINATE:
        text += " 买盘占优"
    return text


def _sentiment_block(sentiment: dict | str, markdown_dir: Path) -> list[str]:
    if _is_missing(sentiment) or not isinstance(sentiment, dict) or not sentiment:
        return ["缺失"]
    lines = [
        f"- 数据日期：{_show(sentiment.get('date'))}",
        f"- 看涨：{_points(sentiment.get('bull'))}",
        f"- 看跌：{_points(sentiment.get('bear'))}",
        f"- 横盘：{_points(sentiment.get('flat'))}",
        f"- 多空差：{_points(sentiment.get('spread'))}",
    ]
    chart = sentiment.get("chart")
    if _is_missing(chart) or not chart:
        lines.append("- 图：缺失")
    else:
        lines.append(f"- 图：![]({_chart_href(str(chart), markdown_dir)})")
    return lines


def _chart_href(chart: str, markdown_dir: Path) -> str:
    path = Path(chart)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    try:
        return Path(os.path.relpath(path, markdown_dir)).as_posix()
    except ValueError:
        return path.as_uri()


def _points(value: object) -> str:
    if value is None or _is_missing(value):
        return "缺失"
    return f"{float(value):.1f}%"


def _commentary_block(commentary: Commentary) -> list[str]:
    if commentary.is_missing():
        return ["缺失"]
    return [commentary.text]


def _ranks_block(ranks: dict | str) -> list[str]:
    if _is_missing(ranks) or not isinstance(ranks, dict):
        return ["缺失"]
    daily = ranks.get("daily")
    rps = ranks.get("rps")
    lines: list[str] = []
    for key, label in _KINDS:
        lines.append(f"### {label}")
        lines.append("")
        for period_label, period in _RANK_PERIODS:
            lines.append(f"#### {period_label}")
            lines.append("")
            board = _board_for(daily, rps, key, period)
            lines.extend(_board_lines(board, with_rps=period is not None))
            lines.append("")
    return lines


def _board_for(daily: object, rps: object, kind: str, period: int | None) -> object:
    source = daily if period is None else rps
    if _is_missing(source) or not isinstance(source, dict):
        return MISSING
    group = source.get(kind)
    if _is_missing(group) or not isinstance(group, dict):
        return MISSING
    if period is None:
        return group
    return group.get(period, MISSING)


def _board_lines(board: object, *, with_rps: bool) -> list[str]:
    if _is_missing(board) or not isinstance(board, dict):
        return ["缺失"]
    lines = []
    for index, item in enumerate(board.get("items") or [], start=1):
        pct = _change(item.get("pct"))
        if with_rps:
            lines.append(f"{index}. {item.get('name')} {pct} RPS {_show(item.get('rps'))}")
        else:
            lines.append(f"{index}. {item.get('name')} {pct}")
    if board.get("flag") == SHORT_LIST:
        lines.append("（不足 10 个）")
    if not lines:
        return ["缺失"]
    return lines


def _change(value: object) -> str:
    if value is None or _is_missing(value):
        return "缺失"
    return f"{float(value) * 100:.2f}%"
