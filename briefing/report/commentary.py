"""Write the market commentary from numbers already on the draft.

The model callable is replaceable. This module does not decide whether the
wording passes: that is Evaluator check 8. It also does not create or edit
the day's markdown.
"""

from __future__ import annotations

import json

from briefing.core.models import Commentary, Draft, Snapshot, missing_commentary

_SIGNAL_FIELDS = ("daily_buy", "weekly_buy", "above_rising_ma5")
_BREADTH_FIELDS = ("net", "up4", "down4", "ratio5", "ratio10", "up25", "down25", "diff25")
_MA50_FIELDS = ("hs300", "chinext", "all_a")
_SENTIMENT_FIELDS = ("bull", "bear", "flat", "spread")
_MISSING = "missing"


def write_commentary(draft: Draft, *, complete=None, judge=None) -> Commentary:
    """Fill the commentary slot from ``complete(prompt)``.

    ``complete`` returns ``{"text", "metrics_used"}``. When it is missing,
    raises, or returns an unusable payload, the slot is marked missing and
    the snapshot numbers stay as they are.

    ``judge(text, metrics_used)`` is the Evaluator's rejection. A non-empty
    reason is sent back for one rewrite. A second rejection, or a second
    model failure, marks the slot missing.
    """
    if complete is None:
        draft.commentary = missing_commentary()
        return draft.commentary
    first = _complete(draft, complete, rejection=None)
    if first is None:
        draft.commentary = missing_commentary()
        return draft.commentary
    reason = _rejected(judge, first) if judge is not None else ""
    if reason:
        second = _complete(draft, complete, rejection=reason)
        if second is None or _rejected(judge, second):
            draft.commentary = missing_commentary()
            return draft.commentary
        draft.commentary = second
        return second
    draft.commentary = first
    return first


def allowed_metric_names(snapshot: Snapshot | dict) -> set[str]:
    """Metric names check 8 may accept for this snapshot."""
    data = _as_dict(snapshot)
    names = {name for name, _value in _metric_entries(data)}
    names.update(_bare_signal_fields(data))
    names.update(_rank_codes(data.get("ranks")))
    return names


def _complete(draft: Draft, complete, rejection: str | None) -> Commentary | None:
    try:
        payload = complete(_prompt(draft, rejection))
    except Exception:
        return None
    return _parse(payload)


def _rejected(judge, commentary: Commentary) -> str:
    reason = judge(commentary.text, list(commentary.metrics_used))
    if not reason:
        return ""
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return "评论未通过需求检查第 8 条"


def _parse(payload: object) -> Commentary | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    metrics = payload.get("metrics_used")
    if not isinstance(text, str) or not text.strip():
        return None
    if not isinstance(metrics, list) or any(not isinstance(item, str) or not item.strip() for item in metrics):
        return None
    return Commentary(text=text.strip(), metrics_used=list(metrics))


def _prompt(draft: Draft, rejection: str | None) -> str:
    data = _as_dict(draft.snapshot)
    data["sentiment"] = draft.sentiment
    present: list[tuple[str, str]] = []
    missing: list[str] = []
    for name, value in _metric_entries(data):
        if _missing_metric(value):
            missing.append(name)
        else:
            present.append((name, _display(value)))
    lines = [
        "只根据下面已经算出的数字写一段市场评论。不产生新的市场事实。",
        "正文用中文写成一段话。不要把 net、up4 这类指标名写进正文，指标名只放在 metrics_used。",
        "括号里是指标含义。正文按这个含义写，不要把不同指标说成同一个差额。",
        "正文可以写交易日、情绪数据日期、「5日」「10日」「60日」以及百分比。允许写「买盘占优」。",
        "metrics_used 的每一项必须是「可用指标」中的指标名。",
        "禁止编造市场数据、涨跌幅、指数点位、成交额、市场宽度、行业或概念数据，以及可用指标里没有的数值。",
        "禁止买入或卖出建议、具体买卖价格和仓位建议。",
        "缺失项不得写成结论。",
        "",
        f"交易日：{draft.snapshot.on_date}",
    ]
    if isinstance(draft.sentiment, dict) and isinstance(draft.sentiment.get("date"), str):
        lines.append(f"情绪数据日期：{draft.sentiment['date']}")
    lines.extend(["", "可用指标："])
    lines.extend(f"- {_glossed(name, value)}" for name, value in present)
    lines.extend(["", "缺失项："])
    lines.extend(f"- {name}" for name in _unique(missing))
    if rejection:
        lines.extend(["", f"上次未通过的原因：{rejection}", "请按该原因重写一次。"])
    lines.extend(["", '返回 JSON：{"text": "评论正文", "metrics_used": ["指标名"]}'])
    return "\n".join(lines)


def _glossed(name: str, value: str) -> str:
    gloss = _GLOSS.get(name)
    shown = f"{name}={value}"
    if not gloss:
        return shown
    return f"{shown}（{gloss}）"


_GLOSS = {
    "hs300.daily_buy": "沪深300日线条件，取值为 YES 或 NO",
    "hs300.weekly_buy": "沪深300周线条件，取值为 YES 或 NO",
    "hs300.above_rising_ma5": "沪深300收盘是否在上升的5日均线之上，取值为 YES 或 NO",
    "chinext.daily_buy": "创业板指日线条件，取值为 YES 或 NO",
    "chinext.weekly_buy": "创业板指周线条件，取值为 YES 或 NO",
    "chinext.above_rising_ma5": "创业板指收盘是否在上升的5日均线之上，取值为 YES 或 NO",
    "net": "52周新高家数减去新低家数，不是当日涨跌家数之差",
    "up4": "当日收盘较前一日上涨至少4%的家数",
    "down4": "当日收盘较前一日下跌至少4%的家数",
    "ratio5": "最近5个交易日，4%上涨家数之和除以下跌家数之和",
    "ratio10": "最近10个交易日，4%上涨家数之和除以下跌家数之和",
    "up25": "按沪深300日历，相对60个交易日前收盘价上涨至少25%的家数",
    "down25": "按沪深300日历，相对60个交易日前收盘价下跌至少25%的家数",
    "diff25": "上涨至少25%的家数减去下跌至少25%的家数",
    "ma50.hs300": "沪深300里收盘价在自身50日均线之上的家数/成分股数",
    "ma50.chinext": "创业板里收盘价在自身50日均线之上的家数/创业板股票数",
    "ma50.all_a": "沪深A股里收盘价在自身50日均线之上的家数/沪深A股数",
    "bull": "情绪调查看涨百分比",
    "bear": "情绪调查看跌百分比",
    "flat": "情绪调查横盘百分比",
    "spread": "情绪看涨百分比减去看跌百分比",
}


def _metric_entries(data: dict) -> list[tuple[str, object]]:
    entries: list[tuple[str, object]] = []
    signals = data.get("signals") or {}
    if isinstance(signals, dict):
        for index, fields in signals.items():
            if not isinstance(fields, dict):
                continue
            for field in _SIGNAL_FIELDS:
                if field in fields:
                    entries.append((f"{index}.{field}", fields[field]))
    breadth = data.get("breadth") or {}
    if isinstance(breadth, dict):
        for field in _BREADTH_FIELDS:
            if field in breadth:
                entries.append((field, breadth[field]))
    ma50 = data.get("ma50") or {}
    if isinstance(ma50, dict):
        for field in _MA50_FIELDS:
            if field in ma50:
                entries.append((f"ma50.{field}", ma50[field]))
    sentiment = data.get("sentiment")
    if isinstance(sentiment, str) and sentiment.strip().lower() == _MISSING:
        entries.extend((field, _MISSING) for field in _SENTIMENT_FIELDS)
    elif isinstance(sentiment, dict):
        for field in _SENTIMENT_FIELDS:
            if field in sentiment:
                entries.append((field, sentiment[field]))
    entries.extend(_rank_entries(data.get("ranks")))
    return entries


def _bare_signal_fields(data: dict) -> set[str]:
    names: set[str] = set()
    signals = data.get("signals") or {}
    if isinstance(signals, dict):
        for fields in signals.values():
            if isinstance(fields, dict):
                names.update(field for field in _SIGNAL_FIELDS if field in fields)
    return names


def _rank_entries(ranks: object) -> list[tuple[str, object]]:
    entries: list[tuple[str, object]] = []
    for item in _rank_items(ranks):
        name = item.get("name")
        code = item.get("code")
        pct = item.get("pct")
        if pct is None:
            pct = _MISSING
        label = name.strip() if isinstance(name, str) and name.strip() else ""
        if not label and isinstance(code, str) and code.strip():
            label = code.strip()
        if label:
            entries.append((label, pct))
    return entries


def _rank_codes(ranks: object) -> set[str]:
    codes: set[str] = set()
    for item in _rank_items(ranks):
        code = item.get("code")
        if isinstance(code, str) and code.strip():
            codes.add(code.strip())
    return codes


def _rank_items(ranks: object) -> list[dict]:
    items: list[dict] = []
    if not isinstance(ranks, dict):
        return items
    for family in ("daily", "rps"):
        groups = ranks.get(family) or {}
        if not isinstance(groups, dict):
            continue
        for kind in ("industry", "concept"):
            group = groups.get(kind)
            for board in _boards(group):
                for item in board.get("items") or []:
                    if isinstance(item, dict):
                        items.append(item)
    return items


def _boards(group: object) -> list[dict]:
    if not isinstance(group, dict):
        return []
    if "items" in group:
        return [group]
    return [board for board in group.values() if isinstance(board, dict)]


def _missing_metric(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() == _MISSING
    if not isinstance(value, dict):
        return False
    if "flag" in value or "value" in value:
        if value.get("flag") == "no_down_4":
            return False
        return value.get("value") is None
    if "above" in value or "total" in value:
        return _missing_metric(value.get("above")) or _missing_metric(value.get("total"))
    return False


def _display(value: object) -> str:
    if isinstance(value, dict) and ("above" in value or "total" in value):
        return f"{_literal(value.get('above'))}/{_literal(value.get('total'))}"
    if isinstance(value, dict) and value.get("flag") == "no_down_4":
        return "无跌幅≥4%"
    if isinstance(value, dict) and ("flag" in value or "value" in value):
        shown = _literal(value.get("value"))
        if value.get("flag") == "buyers_dominate":
            return f"{shown} 买盘占优"
        return shown
    return _literal(value)


def _literal(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _unique(names: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def _as_dict(snapshot: Snapshot | dict) -> dict:
    if isinstance(snapshot, Snapshot):
        return {
            "signals": snapshot.signals,
            "breadth": snapshot.breadth,
            "ma50": snapshot.ma50,
            "ranks": snapshot.ranks,
        }
    if isinstance(snapshot, dict):
        return dict(snapshot)
    return {}
