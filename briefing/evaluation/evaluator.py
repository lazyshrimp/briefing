"""Judge one written briefing. This module does not edit the file or any number."""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

from briefing.report.commentary import allowed_metric_names
from briefing.report.writer import SECTIONS, _KINDS, _RANK_PERIODS

_INDEX_LABELS = {"hs300": "沪深300", "chinext": "创业板指"}
_SIGNAL_LABELS = (
    ("daily_buy", "Daily Buy Signal"),
    ("weekly_buy", "Weekly Buy Signal"),
    ("above_rising_ma5", "Price Action Above Rising 5-DMA"),
)
_MA50_LABELS = (
    ("hs300", "沪深300 50日线以上比例"),
    ("chinext", "创业板 50日线以上比例"),
    ("all_a", "沪深 50日线以上比例"),
)
_PERIOD_LABELS = {label: period for label, period in _RANK_PERIODS}
_KIND_LABELS = {label: key for key, label in _KINDS}
_MISSING = "缺失"
_NO_DOWN = "无跌幅≥4%"
_BUYERS = "买盘占优"
_ROW = re.compile(r"^\d+\.\s+(.+?)\s+(缺失|-?\d+\.\d+%)(?:\s+RPS\s+\S+)?$")
_FRACTION = re.compile(r"^(-?\d+\.\d+)%（(-?\d+(?:\.\d+)?) / (-?\d+(?:\.\d+)?)）$")
_TWO_DECIMALS = re.compile(r"^-?\d+\.\d{2}$")


def evaluate_briefing(
    briefing_path: str | Path,
    snapshot: dict,
    reference: dict | None,
    *,
    context: dict,
) -> dict:
    """Return PASS, FAIL, or STOP.

    Check 8 reads the 市场评论 section and ``context["metrics_used"]``.
    Without that list the check stays unchecked, so the status cannot be PASS.
    """
    try:
        resolved = reference
        if resolved is None:
            from briefing.evaluation.recompute import build_reference

            resolved = build_reference(context["tdx_dir"], context["on_date"])
        return _evaluate(Path(briefing_path), snapshot, resolved, context)
    except Exception as exc:
        return {
            "status": "STOP",
            "requirement_failures": [],
            "sanity_failures": [],
            "not_checked": [],
            "details": {"evaluator_error": f"{type(exc).__name__}: {exc}"},
        }


def _evaluate(path: Path, snapshot: dict, reference: dict, context: dict) -> dict:
    failures: list[int] = []
    sanity: list[str] = []
    details: dict = {}
    not_checked: list[int] = []
    text = path.read_text(encoding="utf-8") if path.is_file() else None
    trading = str(context.get("is_trading_day", "")).lower() == "trading_day"
    day_file = Path(context["output_dir"]) / f"{context['on_date']}.md"

    if trading != day_file.is_file():
        _fail(failures, details, 1, "交易日应有且仅在交易日有该日简报" if trading else "非交易日不应有该日简报")
    if text is None:
        pending = [number for number in range(1, 12) if number not in failures]
        not_checked = sorted(set(not_checked + pending))
        _sanity_schema(snapshot, context, sanity, details)
        return _result(failures, sanity, not_checked, details)

    sections = _sections(text)
    _check_signals(sections.get(SECTIONS[0], ""), snapshot, reference, failures, details)
    _check_ma50(sections.get(SECTIONS[1], ""), reference, failures, details)
    _check_counts(sections.get(SECTIONS[1], ""), reference, failures, details)
    _check_sentiment(path, sections.get(SECTIONS[2], ""), context, failures, details)
    _check_commentary(sections.get(SECTIONS[3], ""), snapshot, context, failures, details, not_checked)
    _check_ranks(sections.get(SECTIONS[4], ""), snapshot, reference, failures, details)
    _check_chart_window(context, failures, sanity, details)
    _check_missing_marks(sections, snapshot, reference, failures, details)
    _sanity_schema(snapshot, context, sanity, details)
    _sanity_identity(snapshot, sanity, details)
    _sanity_rounding(text, sanity, details)
    return _result(failures, sanity, sorted(not_checked), details)


def _result(failures: list[int], sanity: list[str], not_checked: list[int], details: dict) -> dict:
    clean = not failures and not sanity and not not_checked
    return {
        "status": "PASS" if clean else "FAIL",
        "requirement_failures": failures,
        "sanity_failures": sanity,
        "not_checked": not_checked,
        "details": details,
    }


def _fail(bucket: list, details: dict, key, message: str) -> None:
    if key not in bucket:
        bucket.append(key)
    details.setdefault(key, message)


def _sections(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for chunk in re.split(r"\n(?=## )", text):
        if not chunk.startswith("## "):
            continue
        title, _, body = chunk.partition("\n")
        found[title[3:].strip()] = body
    return found


def _field(section: str, label: str) -> str | None:
    prefix = f"- {label}："
    for line in section.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _is_missing(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() == "missing"


def _check_signals(section: str, snapshot: dict, reference: dict, failures: list[int], details: dict) -> None:
    got = _index_values(section)
    for key in ("hs300", "chinext"):
        expected = (reference.get("signals") or {}).get(key) or {}
        for field, _label in _SIGNAL_LABELS:
            shown = got.get(key, {}).get(field)
            if shown == _MISSING:
                continue
            if shown != expected.get(field) or shown not in {"YES", "NO"}:
                _fail(failures, details, 2, f"{_INDEX_LABELS[key]} 的 {_label} 与复算不一致")


def _index_values(section: str) -> dict[str, dict[str, str]]:
    current = None
    found: dict[str, dict[str, str]] = {}
    labels = {label: key for key, label in _INDEX_LABELS.items()}
    signals = {label: key for key, label in _SIGNAL_LABELS}
    for line in section.splitlines():
        if line.startswith("### "):
            current = labels.get(line[4:].strip())
            if current:
                found.setdefault(current, {})
            continue
        if current is None or not line.startswith("- "):
            continue
        label, _, value = line[2:].partition("：")
        field = signals.get(label)
        if field:
            found[current][field] = value.strip()
    return found


def _check_ma50(section: str, reference: dict, failures: list[int], details: dict) -> None:
    ratios = reference.get("ma50") or {}
    for key, label in _MA50_LABELS:
        shown = _field(section, label)
        item = ratios.get(key)
        if shown == _MISSING or _is_missing(item) or not isinstance(item, dict) or item.get("above") is None:
            if shown == _MISSING:
                continue
            _fail(failures, details, 3, f"{label} 与复算不一致")
            continue
        match = _FRACTION.match(shown or "")
        above = _number(item.get("above"))
        total = _number(item.get("total"))
        if match is None or above is None or total is None or total <= 0:
            _fail(failures, details, 3, f"{label} 与复算不一致")
            continue
        if _number(match.group(2)) != above or _number(match.group(3)) != total:
            _fail(failures, details, 3, f"{label} 的分子或分母与复算不一致")
            continue
        expected = f"{above / total * 100:.2f}"
        if match.group(1) != expected:
            _fail(failures, details, 3, f"{label} 的百分比不是分子除以分母后的两位小数")


def _check_counts(section: str, reference: dict, failures: list[int], details: dict) -> None:
    shown = _field(section, "当日4%+涨/跌家数")
    if shown != _MISSING:
        parts = _pair(shown)
        if parts != (reference.get("up4"), reference.get("down4")):
            _fail(failures, details, 4, "当日4%涨跌家数与复算不一致")
    for number, label, key in ((5, "4%突破比率（5日）", "ratio5"), (10, "4%突破比率（10日）", "ratio10")):
        _check_ratio(section, label, reference.get(key) or {}, number, failures, details)
    counts = _pair(_field(section, "滚动60日涨/跌25%家数"))
    diff = _field(section, "60日25%多空差")
    up25, down25 = reference.get("up25"), reference.get("down25")
    if counts == (_MISSING, _MISSING) or diff == _MISSING:
        return
    if not isinstance(up25, int) or not isinstance(down25, int) or counts != (up25, down25) or diff != str(up25 - down25):
        _fail(failures, details, 6, "60日25%涨跌家数或差值与复算不一致")


def _check_ratio(section: str, label: str, counts: dict, number: int, failures: list[int], details: dict) -> None:
    shown = _field(section, label)
    if shown == _MISSING:
        return
    down = counts.get("down")
    up = counts.get("up")
    if down == 0:
        if shown != _NO_DOWN:
            _fail(failures, details, 5, f"{number}日跌家数之和为0时未写{_NO_DOWN}")
        return
    if not isinstance(up, int) or not isinstance(down, int) or down == 0:
        _fail(failures, details, 5, f"{number}日突破比率与复算不一致")
        return
    value = up / down
    expected = f"{value:.2f}"
    marked = shown.endswith(f" {_BUYERS}") if shown else False
    number_text = shown[: -len(f" {_BUYERS}")].strip() if marked else shown
    if number_text != expected or (value > 1 and not marked):
        _fail(failures, details, 5, f"{number}日突破比率与涨跌家数之和的商不一致")


def _pair(shown: str | None) -> tuple:
    if shown == _MISSING:
        return (_MISSING, _MISSING)
    if not shown or " / " not in shown:
        return (None, None)
    left, right = shown.split(" / ", 1)
    return (_int_or_none(left), _int_or_none(right))


def _check_sentiment(path: Path, section: str, context: dict, failures: list[int], details: dict) -> None:
    labels = ("数据日期", "看涨", "看跌", "横盘", "多空差")
    values = {label: _field(section, label) for label in labels}
    chart = _field(section, "图")
    if any(value in (None, _MISSING) for value in values.values()) or chart in (None, _MISSING):
        _fail(failures, details, 7, "情绪块缺数据日期、百分比、多空差或图")
        return
    bull, bear, spread = _percent(values["看涨"]), _percent(values["看跌"]), _percent(values["多空差"])
    if bull is None or bear is None or spread is None or f"{bull - bear:.1f}" != f"{spread:.1f}":
        _fail(failures, details, 7, "情绪多空差不等于看涨减看跌")
    if not _chart_file(path, chart).is_file():
        _fail(failures, details, 7, "情绪图链接没有指向实际文件")
    if context.get("chart_redrawn") and not context.get("new_sentiment_week"):
        _fail(failures, details, 7, "同一周重复出了新的情绪图")


def _chart_file(markdown: Path, chart: str) -> Path:
    href = chart
    if href.startswith("![](") and href.endswith(")"):
        href = href[4:-1]
    elif "图：" in href:
        href = href.split("图：", 1)[1].strip()
    if href.startswith("![](") and href.endswith(")"):
        href = href[4:-1]
    if href.startswith("file:"):
        local = unquote(urlparse(href).path)
        if local.startswith("/") and len(local) > 2 and local[2] == ":":
            local = local[1:]
        return Path(local)
    return (markdown.parent / href).resolve()


def _check_ranks(section: str, snapshot: dict, reference: dict, failures: list[int], details: dict) -> None:
    parsed = _parse_boards(section)
    ranks = reference.get("ranks") or {}
    stored = snapshot.get("ranks") or {}
    for kind in ("industry", "concept"):
        _check_board(
            parsed.get(kind, {}).get("daily"),
            _items(stored, "daily", kind, None),
            (ranks.get("daily") or {}).get(kind) or [],
            failures,
            details,
        )
        for period in (5, 10, 15, 20):
            _check_board(
                parsed.get(kind, {}).get(period),
                _items(stored, "rps", kind, period),
                ((ranks.get("rps") or {}).get(kind) or {}).get(period) or [],
                failures,
                details,
            )


def _items(stored: dict, family: str, kind: str, period: int | None) -> list[dict]:
    group = (stored.get(family) or {}).get(kind)
    if not isinstance(group, dict):
        return []
    board = group if period is None else group.get(period)
    if not isinstance(board, dict):
        return []
    return list(board.get("items") or [])


def _check_board(parsed, snapshot_items: list[dict], reference_rows: list[dict], failures, details) -> None:
    if parsed is None:
        if reference_rows:
            _fail(failures, details, 9, "榜单缺失，与复算出的名次不一致")
        return
    codes = _codes_for(parsed, snapshot_items)
    expected = [row["code"] for row in reference_rows]
    if codes != expected:
        _fail(failures, details, 9, "榜单顺序与复算的涨跌幅或 RPS 不一致")
        return
    for shown, row in zip(parsed, reference_rows):
        if shown[1] != _pct_text(row.get("pct")):
            _fail(failures, details, 9, "名称旁的涨跌幅与板块指数复算不一致")
            return


def _codes_for(parsed: list[tuple[str, str]], items: list[dict]) -> list[str] | None:
    pool = list(items)
    codes = []
    for name, _pct in parsed:
        found = next((item for item in pool if item.get("name") == name), None)
        if found is None:
            return None
        pool.remove(found)
        codes.append(found.get("code"))
    return codes


def _pct_text(value: object) -> str:
    if value is None or _is_missing(value):
        return _MISSING
    return f"{float(value) * 100:.2f}%"


def _parse_boards(section: str) -> dict:
    parsed: dict = {}
    kind = None
    period = None
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            kind = _KIND_LABELS.get(stripped[4:].strip())
            if kind:
                parsed.setdefault(kind, {})
            period = None
            continue
        if stripped.startswith("#### "):
            period = _PERIOD_LABELS.get(stripped[5:].strip())
            if kind and period is not None or (kind and stripped[5:].strip() == "当日"):
                parsed[kind][period if period is not None else "daily"] = []
            continue
        if kind is None or not parsed.get(kind):
            continue
        slot = "daily" if period is None else period
        if slot not in parsed[kind]:
            continue
        if stripped == _MISSING and parsed[kind][slot] == []:
            parsed[kind][slot] = None
            continue
        match = _ROW.match(stripped)
        if match and isinstance(parsed[kind][slot], list):
            parsed[kind][slot].append((match.group(1), match.group(2)))
    return parsed


def _check_chart_window(context: dict, failures: list[int], sanity: list[str], details: dict) -> None:
    counted = _window_count(Path(context["sentiment_csv"]))
    points = context.get("chart_points")
    if points != counted:
        _fail(failures, details, 10, "情绪图点数与最近两年的 CSV 行数不一致")
        _fail(sanity, details, "chart_point_count", "情绪图点数与最近两年的 CSV 行数不一致")
    else:
        return


def _window_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return 0
    latest = date.fromisoformat(rows[-1]["date"])
    try:
        start = latest.replace(year=latest.year - 2)
    except ValueError:
        start = latest.replace(year=latest.year - 2, day=28)
    return sum(1 for row in rows if date.fromisoformat(row["date"]) >= start)


def _check_missing_marks(
    sections: dict[str, str],
    snapshot: dict,
    reference: dict,
    failures: list[int],
    details: dict,
) -> None:
    cells = _snapshot_cells(snapshot)
    shown = _shown_cells(sections)
    _mark_pair(cells, shown, "breadth:up4", "breadth:down4", failures, details)
    _mark_pair(cells, shown, "breadth:up25", "breadth:down25", failures, details)
    for key in ("breadth:up4", "breadth:down4", "breadth:up25", "breadth:down25"):
        cells.pop(key, None)
    for key, value in cells.items():
        _mark_cell(value, shown.get(key), failures, details)
    _mark_ranks(sections, snapshot, failures, details)
    _mark_reference_hidden(sections, reference, failures, details)


def _mark_reference_hidden(sections: dict[str, str], reference: dict, failures: list[int], details: dict) -> None:
    """Fail check 11 when a recomputed value is printed as 缺失."""
    trend = sections.get(SECTIONS[0], "")
    breadth = sections.get(SECTIONS[1], "")
    got = _index_values(trend)
    for key in ("hs300", "chinext"):
        expected = (reference.get("signals") or {}).get(key) or {}
        if not isinstance(expected, dict):
            continue
        for field, label in _SIGNAL_LABELS:
            if expected.get(field) in {"YES", "NO"} and got.get(key, {}).get(field) == _MISSING:
                _fail(failures, details, 11, f"复算有值，简报写成了缺失：{_INDEX_LABELS[key]} {label}")
    for key, label in _MA50_LABELS:
        item = (reference.get("ma50") or {}).get(key)
        if isinstance(item, dict) and item.get("above") is not None and _field(breadth, label) == _MISSING:
            _fail(failures, details, 11, f"复算有值，简报写成了缺失：{label}")
    if isinstance(reference.get("up4"), int) and isinstance(reference.get("down4"), int):
        if _field(breadth, "当日4%+涨/跌家数") == _MISSING:
            _fail(failures, details, 11, "复算有值，简报写成了缺失：当日4%+涨/跌家数")
    for label, key in (("4%突破比率（5日）", "ratio5"), ("4%突破比率（10日）", "ratio10")):
        counts = reference.get(key) or {}
        if isinstance(counts, dict) and isinstance(counts.get("up"), int) and isinstance(counts.get("down"), int):
            if _field(breadth, label) == _MISSING:
                _fail(failures, details, 11, f"复算有值，简报写成了缺失：{label}")
    if isinstance(reference.get("up25"), int) and isinstance(reference.get("down25"), int):
        if _field(breadth, "滚动60日涨/跌25%家数") == _MISSING:
            _fail(failures, details, 11, "复算有值，简报写成了缺失：滚动60日涨/跌25%家数")
        if _field(breadth, "60日25%多空差") == _MISSING:
            _fail(failures, details, 11, "复算有值，简报写成了缺失：60日25%多空差")


def _mark_pair(cells: dict, shown: dict, left: str, right: str, failures: list[int], details: dict) -> None:
    missing = any(_is_missing(cells.get(key)) or cells.get(key) is None for key in (left, right))
    display = shown.get(left)
    if missing:
        _mark_cell("missing", display, failures, details)
    else:
        _mark_cell(cells.get(left), display, failures, details)


def _mark_cell(value: object, display: str | None, failures: list[int], details: dict) -> None:
    if _is_missing(value) or value is None:
        if display != _MISSING:
            _fail(failures, details, 11, "snapshot 中缺失的字段没有写成缺失")
    elif display == _MISSING or display is None:
        _fail(failures, details, 11, "snapshot 中有值的字段在简报里写成了缺失")


def _mark_ranks(sections: dict[str, str], snapshot: dict, failures: list[int], details: dict) -> None:
    parsed = _parse_boards(sections.get(SECTIONS[4], ""))
    ranks = snapshot.get("ranks") or {}
    slots = (("daily", "daily", None), (5, "rps", 5), (10, "rps", 10), (15, "rps", 15), (20, "rps", 20))
    for kind in ("industry", "concept"):
        for slot, family, period in slots:
            rows = parsed.get(kind, {}).get(slot, [])
            by_name = {} if rows is None else {name: pct for name, pct in rows}
            for item in _items(ranks, family, kind, period):
                shown = _MISSING if rows is None else by_name.get(item.get("name"))
                _mark_cell(item.get("pct"), shown, failures, details)


def _snapshot_cells(snapshot: dict) -> dict[str, object]:
    cells: dict[str, object] = {}
    signals = snapshot.get("signals") or {}
    for index, fields in signals.items():
        if not isinstance(fields, dict):
            cells[f"signal:{index}"] = fields
            continue
        for field, _label in _SIGNAL_LABELS:
            cells[f"signal:{index}:{field}"] = fields.get(field)
    breadth = snapshot.get("breadth") or {}
    for key in ("net", "up4", "down4", "ratio5", "ratio10", "up25", "down25", "diff25"):
        cells[f"breadth:{key}"] = breadth.get(key)
    ma50 = snapshot.get("ma50") or {}
    for key, _label in _MA50_LABELS:
        cells[f"ma50:{key}"] = ma50.get(key)
    sentiment = snapshot.get("sentiment")
    if isinstance(sentiment, dict):
        for key in ("date", "bull", "bear", "flat", "spread", "chart"):
            cells[f"sentiment:{key}"] = sentiment.get(key)
    else:
        for key in ("date", "bull", "bear", "flat", "spread", "chart"):
            cells[f"sentiment:{key}"] = sentiment
    return cells


def _shown_cells(sections: dict[str, str]) -> dict[str, str | None]:
    trend = sections.get(SECTIONS[0], "")
    breadth = sections.get(SECTIONS[1], "")
    sentiment = sections.get(SECTIONS[2], "")
    shown: dict[str, str | None] = {}
    signals = _index_values(trend)
    for index in ("hs300", "chinext"):
        for field, _label in _SIGNAL_LABELS:
            shown[f"signal:{index}:{field}"] = signals.get(index, {}).get(field)
    shown["breadth:net"] = _field(breadth, "52周新高减新低")
    for key, label in _MA50_LABELS:
        shown[f"ma50:{key}"] = _field(breadth, label)
    pair = _field(breadth, "当日4%+涨/跌家数")
    shown["breadth:up4"] = pair
    shown["breadth:down4"] = pair
    shown["breadth:ratio5"] = _field(breadth, "4%突破比率（5日）")
    shown["breadth:ratio10"] = _field(breadth, "4%突破比率（10日）")
    quarter = _field(breadth, "滚动60日涨/跌25%家数")
    shown["breadth:up25"] = quarter
    shown["breadth:down25"] = quarter
    shown["breadth:diff25"] = _field(breadth, "60日25%多空差")
    whole = sentiment.strip() == _MISSING
    for key, label in (
        ("date", "数据日期"),
        ("bull", "看涨"),
        ("bear", "看跌"),
        ("flat", "横盘"),
        ("spread", "多空差"),
        ("chart", "图"),
    ):
        shown[f"sentiment:{key}"] = _MISSING if whole else _field(sentiment, label)
    return shown


def _check_commentary(
    section: str,
    snapshot: dict,
    context: dict,
    failures: list[int],
    details: dict,
    not_checked: list[int],
) -> None:
    """Check 8. Layer 2 does not require every number in the text to be copied from the snapshot."""
    if "metrics_used" not in context:
        not_checked.append(8)
        return
    metrics = context["metrics_used"]
    if not isinstance(metrics, list) or any(not isinstance(item, str) for item in metrics):
        _fail(failures, details, 8, "metrics_used 不是指标名列表")
        return
    unknown = [item for item in metrics if item not in allowed_metric_names(snapshot)]
    if unknown:
        _fail(failures, details, 8, f"metrics_used 含 snapshot 之外的指标：{unknown[0]}")
    text = section.strip()
    if not text:
        _fail(failures, details, 8, "市场评论为空")
        return
    if text == _MISSING:
        return
    problem = _commentary_problem(text, snapshot)
    if problem:
        _fail(failures, details, 8, problem)


def _commentary_problem(text: str, snapshot: dict) -> str | None:
    scanned = text.replace(_BUYERS, "")
    if re.search(r"买入|卖出|买进|建议买|建议卖|做多|做空", scanned):
        return "评论含有买入或卖出建议"
    if re.search(r"仓位|满仓|半仓|空仓|轻仓|重仓|加仓|减仓|清仓", scanned):
        return "评论含有仓位建议"
    if re.search(r"买入价|卖出价|目标价|买卖价|(?<![\d.])-?\d+(?:\.\d+)?\s*元", scanned):
        return "评论含有具体买卖价格"
    alien = _alien_market_number(text, snapshot)
    if alien:
        return f"评论含有 snapshot 中没有的市场数值：{alien}"
    return None


def _alien_market_number(text: str, snapshot: dict) -> str | None:
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日", " ", text)
    cleaned = re.sub(r"-?\d+(?:\.\d+)?[%％]", " ", cleaned)
    cleaned = re.sub(r"(?<!\d)(?:5|10|15|20|60)日", " ", cleaned)
    known = _snapshot_numbers(snapshot)
    patterns = (
        r"(-?\d+(?:\.\d+)?)\s*点",
        r"点位\s*(-?\d+(?:\.\d+)?)",
        r"成交额\s*(-?\d+(?:\.\d+)?)",
        r"(-?\d+(?:\.\d+)?)\s*(?:万亿|亿元|万元|亿|万)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, cleaned):
            if not _known_number(match.group(1), known):
                return match.group(0).strip()
    return None


def _snapshot_numbers(value: object, found: set[float] | None = None) -> set[float]:
    if found is None:
        found = set()
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return found
    if isinstance(value, (int, float)):
        found.add(float(value))
        return found
    if isinstance(value, dict):
        for item in value.values():
            _snapshot_numbers(item, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _snapshot_numbers(item, found)
    return found


def _known_number(raw: str, known: set[float]) -> bool:
    try:
        number = float(raw)
    except ValueError:
        return False
    return any(abs(number - item) <= 1e-6 for item in known)


def _sanity_schema(snapshot: dict, context: dict, sanity: list[str], details: dict) -> None:
    output = Path(context["output_dir"])
    dated = [path for path in output.glob("*.md") if context["on_date"] in path.name]
    if len(dated) > 1 or not _metrics_ok(snapshot) or not _commentary_fields_ok(context):
        _fail(sanity, details, "schema", "snapshot 字段或该日简报份数不符合约定")


def _commentary_fields_ok(context: dict) -> bool:
    if "metrics_used" not in context:
        return True
    metrics = context["metrics_used"]
    return isinstance(metrics, list) and all(isinstance(item, str) for item in metrics)


def _metrics_ok(snapshot: dict) -> bool:
    signals = snapshot.get("signals") or {}
    for fields in signals.values():
        if not isinstance(fields, dict):
            return _metric(fields)
        if any(not _metric(fields.get(key)) for key, _label in _SIGNAL_LABELS):
            return False
    breadth = snapshot.get("breadth") or {}
    for key in ("net", "up4", "down4", "up25", "down25", "diff25"):
        if not _metric(breadth.get(key)):
            return False
    for key in ("ratio5", "ratio10"):
        if not _ratio_ok(breadth.get(key)):
            return False
    ma50 = snapshot.get("ma50") or {}
    for key, _label in _MA50_LABELS:
        if not _ma50_ok(ma50.get(key)):
            return False
    sentiment = snapshot.get("sentiment")
    if not (_is_missing(sentiment) or isinstance(sentiment, dict)):
        return False
    if isinstance(sentiment, dict):
        for key in ("bull", "bear", "flat", "spread"):
            if not _metric(sentiment.get(key)):
                return False
        chart = sentiment.get("chart")
        if chart in (None, "") or not (_is_missing(chart) or isinstance(chart, str)):
            return False
        if not (_is_missing(sentiment.get("date")) or isinstance(sentiment.get("date"), str)):
            return False
    return _ranks_ok(snapshot.get("ranks") or {})


def _metric(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    return _is_missing(value) or value in {"YES", "NO"}


def _ratio_ok(value: object) -> bool:
    if _is_missing(value):
        return True
    if not isinstance(value, dict):
        return False
    flag = value.get("flag")
    if flag not in {None, "buyers_dominate", "no_down_4"}:
        return False
    number = value.get("value")
    if flag == "no_down_4":
        return number is None
    return isinstance(number, (int, float)) and not isinstance(number, bool)


def _ma50_ok(value: object) -> bool:
    if _is_missing(value):
        return True
    if not isinstance(value, dict):
        return False
    if not _metric(value.get("above")) or not _metric(value.get("total")):
        return False
    pct = value.get("pct")
    return pct is None or _metric(pct)


def _ranks_ok(ranks: dict) -> bool:
    for family in ("daily", "rps"):
        groups = ranks.get(family) or {}
        for kind in ("industry", "concept"):
            group = groups.get(kind)
            if group is None:
                continue
            if not isinstance(group, dict):
                return False
            boards = [group] if family == "daily" else [group.get(period) for period in (5, 10, 15, 20)]
            for board in boards:
                if board is None or _is_missing(board):
                    continue
                if not isinstance(board, dict):
                    return False
                if board.get("flag") not in {None, "short_list"}:
                    return False
                for item in board.get("items") or []:
                    if not isinstance(item.get("name"), str) or not isinstance(item.get("code"), str):
                        return False
                    if not _metric(item.get("pct")):
                        return False
                    if "rps" in item and not _metric(item.get("rps")):
                        return False
    return True


def _sanity_identity(snapshot: dict, sanity: list[str], details: dict) -> None:
    breadth = snapshot.get("breadth") or {}
    up, down, diff = breadth.get("up25"), breadth.get("down25"), breadth.get("diff25")
    if any(_is_missing(value) or not isinstance(value, (int, float)) or isinstance(value, bool) for value in (up, down, diff)):
        return
    if diff != up - down:
        _fail(sanity, details, "internal_identity", "snapshot 里的 25% 差值不等于涨家数减跌家数")


def _sanity_rounding(text: str, sanity: list[str], details: dict) -> None:
    for line in text.splitlines():
        if line.startswith("- 4%突破比率") and _NO_DOWN not in line and _MISSING not in line:
            number = line.split("：", 1)[-1].replace(_BUYERS, "").strip()
            if not _TWO_DECIMALS.match(number):
                _fail(sanity, details, "display_rounding", "突破比率不是两位小数")
        if "50日线以上比例：" in line and _MISSING not in line:
            match = _FRACTION.match(line.split("：", 1)[-1].strip())
            if match is None or not _TWO_DECIMALS.match(match.group(1)):
                _fail(sanity, details, "display_rounding", "50日线百分比不是两位小数")
        match = _ROW.match(line.strip())
        if match and match.group(2) != _MISSING and not match.group(2).endswith("%"):
            _fail(sanity, details, "display_rounding", "榜单涨跌幅不是两位小数")
        if match and match.group(2).endswith("%"):
            if not _TWO_DECIMALS.match(match.group(2)[:-1]):
                _fail(sanity, details, "display_rounding", "榜单涨跌幅不是两位小数")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None or _is_missing(value):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except ValueError:
            return None
    if number.is_integer():
        return float(int(number))
    return number


def _int_or_none(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def _percent(text: str | None) -> float | None:
    if not text or not text.endswith("%"):
        return None
    try:
        return float(text[:-1])
    except ValueError:
        return None
