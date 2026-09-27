"""Assemble an in-memory draft and write it once commentary is present.

The five headings are the blocks in requirement section 3. A missing value
is written as 缺失. The day's file is published by renaming a temporary
file, and only after the commentary slot is filled or marked missing.
"""

from __future__ import annotations

import html
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
    (
        "daily_buy",
        "日线买入信号",
        "收盘价在 10 日均线和 20 日均线之上，并且 10 日均线在 20 日均线之上。相等为否。",
    ),
    (
        "weekly_buy",
        "周线买入信号",
        "收盘价在 10 周均线和 20 周均线之上，并且 10 周均线在 20 周均线之上。周收盘取该周最后一个交易日。相等为否。",
    ),
    (
        "above_rising_ma5",
        "价格在上升的5日均线之上",
        "收盘价在 5 日均线之上，并且 5 日均线高于前一日的 5 日均线。相等为否。",
    ),
)
_RANK_PERIODS = (("当日", None), ("5日", 5), ("10日", 10), ("20日", 20))
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
    page = directory / f"{on_date}.html"
    page_temporary = directory / f".{on_date}.html.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(_render(draft, directory), encoding="utf-8", newline="\n")
        page_temporary.write_text(_render_html(draft, directory), encoding="utf-8", newline="\n")
        os.replace(temporary, target)
        os.replace(page_temporary, page)
    except OSError:
        temporary.unlink(missing_ok=True)
        page_temporary.unlink(missing_ok=True)
        return STOP
    return {"path": str(target), "html": str(page)}


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


def _render_html(draft: Draft, markdown_dir: Path) -> str:
    commentary = draft.commentary
    assert commentary is not None
    on_date = html.escape(draft.snapshot.on_date)
    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>每日简报 {on_date}</title>",
        f"<style>{_PAGE_CSS}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<header>",
        "<p>每日市场简报</p>",
        f"<h1>{on_date}</h1>",
        "</header>",
        _html_signals(draft.snapshot.signals),
        _html_breadth(draft.snapshot.breadth, draft.snapshot.ma50),
        _html_sentiment(draft.sentiment, markdown_dir),
        _html_commentary(commentary),
        _html_ranks(draft.snapshot.ranks),
        "</main>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


_PAGE_CSS = """
:root { color-scheme: dark; }
body { margin: 0; background: #0e1420; color: #e7edf5; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 28px 20px 48px; }
header p { margin: 0; color: #8ea0b8; letter-spacing: 0.08em; }
header h1 { margin: 6px 0 22px; font-size: 32px; }
section { margin: 0 0 22px; padding: 16px 18px; background: #172033; border: 1px solid #2a3952; border-radius: 12px; }
h2 { margin: 0 0 14px; font-size: 18px; }
h3 { margin: 16px 0 8px; font-size: 15px; color: #b7c7dc; }
h4 { margin: 14px 0 6px; font-size: 14px; color: #d5e2f2; }
.indexes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.card { padding: 12px; background: #10192b; border-radius: 10px; }
.signal { display: grid; grid-template-columns: 1fr auto; gap: 8px 16px; padding: 10px 0; border-top: 1px solid #24344c; }
.signal strong { display: block; }
.signal span { color: #9aadc4; font-size: 13px; line-height: 1.45; }
.badge { align-self: center; min-width: 52px; padding: 4px 10px; border-radius: 999px; text-align: center; font-weight: 700; }
.yes { background: #1f7a4d; color: #fff; }
.no { background: #a33b3b; color: #fff; }
.miss { background: #5c6570; color: #fff; }
.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; margin: 0; }
.metrics div { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid #24344c; }
.metrics dt { color: #9aadc4; }
.metrics dd { margin: 0; font-variant-numeric: tabular-nums; }
.note { color: #9aadc4; }
table { width: 100%; border-collapse: collapse; margin: 0 0 8px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #24344c; }
th { color: #8ea0b8; font-weight: 600; }
.up { color: #3dbe7a; }
.down { color: #f06a6a; }
img { max-width: 100%; height: auto; border-radius: 8px; }
@media (max-width: 800px) { .indexes, .metrics, .pair { grid-template-columns: 1fr; } }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
"""


def _html_signals(signals: dict | str) -> str:
    if _is_missing(signals) or not isinstance(signals, dict):
        return "<section><h2>市场趋势</h2><p>缺失</p></section>"
    cards = []
    for key, label in _INDEXES:
        index = signals.get(key)
        rows = []
        if _is_missing(index) or not isinstance(index, dict):
            rows.append("<p>缺失</p>")
        else:
            for field, name, note in _SIGNALS:
                shown = _show(index.get(field))
                rows.append(
                    "<div class=\"signal\">"
                    f"<div><strong>{html.escape(name)}</strong><span>{html.escape(note)}</span></div>"
                    f"{_badge(shown)}"
                    "</div>"
                )
        cards.append(f"<article class=\"card\"><h3>{html.escape(label)}</h3>{''.join(rows)}</article>")
    return "<section><h2>市场趋势</h2><div class=\"indexes\">" + "".join(cards) + "</div></section>"


def _badge(shown: str) -> str:
    kind = {"YES": "yes", "NO": "no"}.get(shown, "miss")
    return f"<b class=\"badge {kind}\">{html.escape(shown)}</b>"


def _html_breadth(breadth: dict | str, ma50: dict | str) -> str:
    rows = [
        ("52周新高减新低", _show(breadth.get("net")) if isinstance(breadth, dict) else "缺失"),
        *_ma50_pairs(ma50),
        ("当日4%+涨/跌家数", _pair(breadth.get("up4"), breadth.get("down4")) if isinstance(breadth, dict) else "缺失"),
        ("4%突破比率（5日）", _ratio(breadth.get("ratio5")) if isinstance(breadth, dict) else "缺失"),
        ("4%突破比率（10日）", _ratio(breadth.get("ratio10")) if isinstance(breadth, dict) else "缺失"),
        ("滚动60日涨/跌25%家数", _pair(breadth.get("up25"), breadth.get("down25")) if isinstance(breadth, dict) else "缺失"),
        ("60日25%多空差", _show(breadth.get("diff25")) if isinstance(breadth, dict) else "缺失"),
    ]
    body = "".join(f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>" for label, value in rows)
    return f"<section><h2>广度</h2><dl class=\"metrics\">{body}</dl></section>"


def _ma50_pairs(ma50: dict | str) -> list[tuple[str, str]]:
    labels = (
        ("hs300", "沪深300 50日线以上比例"),
        ("chinext", "创业板 50日线以上比例"),
        ("all_a", "沪深 50日线以上比例"),
    )
    if _is_missing(ma50) or not isinstance(ma50, dict):
        return [(label, "缺失") for _, label in labels]
    return [(label, _fraction(ma50.get(key))) for key, label in labels]


def _html_sentiment(sentiment: dict | str, markdown_dir: Path) -> str:
    if _is_missing(sentiment) or not isinstance(sentiment, dict) or not sentiment:
        return "<section><h2>投资者情绪</h2><p>缺失</p></section>"
    rows = [
        ("数据日期", _show(sentiment.get("date"))),
        ("看涨", _points(sentiment.get("bull"))),
        ("看跌", _points(sentiment.get("bear"))),
        ("横盘", _points(sentiment.get("flat"))),
        ("多空差", _points(sentiment.get("spread"))),
    ]
    body = "".join(f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>" for label, value in rows)
    chart = sentiment.get("chart")
    if chart is None or _is_missing(chart):
        picture = "<p>图：缺失</p>"
    else:
        href = _chart_href(str(chart), markdown_dir)
        picture = f"<img src=\"{html.escape(href, quote=True)}\" alt=\"投资者情绪图\">"
    return f"<section><h2>投资者情绪</h2><dl class=\"metrics\">{body}</dl>{picture}</section>"


def _html_commentary(commentary: Commentary) -> str:
    if commentary.is_missing():
        text = "缺失"
    else:
        text = commentary.text
    return f"<section><h2>市场评论</h2><p class=\"note\">{html.escape(text)}</p></section>"


def _html_ranks(ranks: dict | str) -> str:
    if _is_missing(ranks) or not isinstance(ranks, dict):
        return "<section><h2>板块与概念</h2><p>缺失</p></section>"
    daily = ranks.get("daily")
    rps = ranks.get("rps")
    blocks = []
    for period_label, period in _RANK_PERIODS:
        columns = []
        for key, label in _KINDS:
            board = _board_for(daily, rps, key, period)
            columns.append(f"<div><h4>{html.escape(label)}</h4>{_html_board(board)}</div>")
        blocks.append(f"<h3>{html.escape(period_label)}</h3><div class=\"pair\">{''.join(columns)}</div>")
    return "<section><h2>板块与概念</h2>" + "".join(blocks) + "</section>"


def _html_board(board: object) -> str:
    if _is_missing(board) or not isinstance(board, dict) or not (board.get("items") or []):
        return "<p>缺失</p>"
    rows = []
    for item in board.get("items") or []:
        pct = _change(item.get("pct"))
        tone = "" if pct == "缺失" else ("down" if pct.startswith("-") else "up")
        name = html.escape(str(item.get("name") or ""))
        rows.append(f"<tr><td>{name}</td><td class=\"{tone}\">{html.escape(pct)}</td></tr>")
    note = "<p class=\"note\">（不足 10 个）</p>" if board.get("flag") == SHORT_LIST else ""
    return "<table><tr><th>名称</th><th>区间涨跌幅</th></tr>" + "".join(rows) + f"</table>{note}"


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
        for field, name, note in _SIGNALS:
            lines.append(f"- {name}：{_show(index.get(field))}")
            lines.append(f"  {note}")
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
    for period_label, period in _RANK_PERIODS:
        lines.append(f"### {period_label}")
        lines.append("")
        for key, label in _KINDS:
            lines.append(f"#### {label}")
            lines.append("")
            board = _board_for(daily, rps, key, period)
            lines.extend(_board_lines(board))
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


def _board_lines(board: object) -> list[str]:
    if _is_missing(board) or not isinstance(board, dict):
        return ["缺失"]
    lines = [f"{index}. {item.get('name')} {_change(item.get('pct'))}" for index, item in enumerate(board.get("items") or [], start=1)]
    if board.get("flag") == SHORT_LIST:
        lines.append("（不足 10 个）")
    if not lines:
        return ["缺失"]
    return lines


def _change(value: object) -> str:
    if value is None or _is_missing(value):
        return "缺失"
    return f"{float(value) * 100:.2f}%"
