"""Restate metrics already listed in the commentary prompt.

This is the stand-in used when no external model is configured. It copies
names and values from the prompt's usable-metric block and does not add a
market number of its own. ``run_daily(complete=None)`` still leaves the
slot missing; the daily entry point passes this function in.
"""

from __future__ import annotations

import re

_LABELS = {
    "hs300.daily_buy": "沪深300日线条件",
    "hs300.weekly_buy": "沪深300周线条件",
    "hs300.above_rising_ma5": "沪深300的5日均线条件",
    "chinext.daily_buy": "创业板指日线条件",
    "chinext.weekly_buy": "创业板指周线条件",
    "chinext.above_rising_ma5": "创业板指的5日均线条件",
    "net": "52周新高减新低",
    "up4": "当日4%以上上涨家数",
    "down4": "当日4%以上下跌家数",
    "ratio5": "5日突破比率",
    "ratio10": "10日突破比率",
    "up25": "60日上涨25%家数",
    "down25": "60日下跌25%家数",
    "diff25": "60日25%差值",
    "ma50.hs300": "沪深300的50日线以上家数",
    "ma50.chinext": "创业板的50日线以上家数",
    "ma50.all_a": "沪深的50日线以上家数",
    "bull": "看涨",
    "bear": "看跌",
    "flat": "横盘",
    "spread": "情绪多空差",
}
_SIGNAL_KEYS = (
    "hs300.daily_buy",
    "hs300.weekly_buy",
    "hs300.above_rising_ma5",
    "chinext.daily_buy",
    "chinext.weekly_buy",
    "chinext.above_rising_ma5",
)
_PERCENT_KEYS = ("bull", "bear", "flat", "spread")
_FORBIDDEN = re.compile(r"买入|卖出|买进|建议买|建议卖|做多|做空|仓位|满仓|半仓|空仓|轻仓|重仓|加仓|减仓|清仓")


def complete_from_prompt(prompt: str) -> dict:
    """Return ``{text, metrics_used}`` using only the prompt's usable metrics."""
    present = _present(prompt)
    text, used = _paragraph(prompt, present)
    return {"text": text, "metrics_used": used}


def _present(prompt: str) -> dict[str, str]:
    usable, _, _rest = prompt.partition("缺失项：")
    _, _, body = usable.partition("可用指标：")
    found: dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        name, separator, value = stripped[2:].partition("=")
        key = name.strip()
        if separator and key and value.strip() and key not in found:
            found[key] = value.strip()
    return found


def _paragraph(prompt: str, present: dict[str, str]) -> tuple[str, list[str]]:
    parts: list[str] = []
    used: list[str] = []
    day = _field(prompt, "交易日")
    if day:
        parts.append(f"交易日 {day}。")
    signals = _clauses(present, _SIGNAL_KEYS, used)
    if signals:
        parts.append("，".join(signals) + "。")
    if "net" in present:
        parts.append(f"52周新高减新低为 {_show_value(present['net'])}。")
        used.append("net")
    if "up4" in present or "down4" in present:
        bits = []
        if "up4" in present:
            bits.append(f"上涨 {_show_value(present['up4'])} 家")
            used.append("up4")
        if "down4" in present:
            bits.append(f"下跌 {_show_value(present['down4'])} 家")
            used.append("down4")
        parts.append("当日4%以上" + "、".join(bits) + "。")
    ratios = _clauses(present, ("ratio5", "ratio10"), used)
    if ratios:
        parts.append("，".join(ratios) + "。")
    window = _clauses(present, ("up25", "down25", "diff25"), used)
    if window:
        parts.append("，".join(window) + "。")
    ma50 = _clauses(present, ("ma50.hs300", "ma50.chinext", "ma50.all_a"), used)
    if ma50:
        parts.append("，".join(ma50) + "。")
    sentiment_day = _field(prompt, "情绪数据日期")
    sentiment = _sentiment(present, used)
    if sentiment_day or sentiment:
        lead = f"情绪数据日期 {sentiment_day}" if sentiment_day else "情绪"
        if sentiment:
            parts.append(lead + "，" + "，".join(sentiment) + "。")
        else:
            parts.append(lead + "。")
    rank = _rank(present)
    if rank is not None:
        name, shown = rank
        sentence = f"当日榜单首位是{name}，涨跌幅 {shown}。"
        if _allowed(sentence):
            parts.append(sentence)
            used.append(name)
    text = "".join(parts).strip()
    if not text or not _allowed(text):
        return "没有可引用的已算指标。", []
    return text, used


def _clauses(present: dict[str, str], keys: tuple[str, ...], used: list[str]) -> list[str]:
    lines = []
    for key in keys:
        if key not in present:
            continue
        lines.append(f"{_LABELS[key]}为 {_show_value(present[key])}")
        used.append(key)
    return lines


def _sentiment(present: dict[str, str], used: list[str]) -> list[str]:
    lines = []
    for key in _PERCENT_KEYS:
        if key not in present:
            continue
        value = present[key] if present[key].endswith("%") else f"{present[key]}%"
        lines.append(f"{_LABELS[key]} {value}")
        used.append(key)
    return lines


def _show_value(value: str) -> str:
    head, separator, tail = value.partition(" ")
    try:
        number = float(head)
    except ValueError:
        return value
    shown = str(int(number)) if number.is_integer() else f"{number:.2f}"
    if not separator:
        return shown
    return f"{shown} {tail}"


def _rank(present: dict[str, str]) -> tuple[str, str] | None:
    for name, value in present.items():
        if name in _LABELS:
            continue
        try:
            number = float(value)
        except ValueError:
            shown = value
        else:
            shown = f"{number * 100:.2f}%"
        return name, shown
    return None


def _field(prompt: str, label: str) -> str:
    prefix = f"{label}："
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _allowed(text: str) -> bool:
    return _FORBIDDEN.search(text.replace("买盘占优", "")) is None
