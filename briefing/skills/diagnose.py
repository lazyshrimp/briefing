"""Classify an evaluator failure. This skill does not edit code or the briefing.

The checklist names the module for each requirement number. It does not open
a file that the checklist does not already name. Extra notes, when the
diagnostic agent has already gathered them, are appended as evidence.
"""

from __future__ import annotations

TAXONOMY = (
    "wrong_file",
    "formula_mismatch",
    "commentary_violation",
    "data_missing",
    "evaluator_error",
)

# check number -> category, module, function, what to look at
_CHECKS = {
    1: (
        "wrong_file",
        "briefing/core/calendar.py",
        "is_trading_day",
        "核对交易日判断，以及 workflow/daily.py 是否只在交易日写出该日简报",
    ),
    2: (
        "formula_mismatch",
        "briefing/analysis/signals.py",
        "index_signals",
        "核对沪深300与创业板指的三条信号和指数日线",
    ),
    3: (
        "formula_mismatch",
        "briefing/analysis/ma50.py",
        "ma50_ratios",
        "核对 50 日线以上比例的分子、分母",
    ),
    4: (
        "formula_mismatch",
        "briefing/analysis/breadth.py",
        "breadth_snapshot",
        "核对当日 4% 涨家数、跌家数",
    ),
    5: (
        "formula_mismatch",
        "briefing/analysis/breadth.py",
        "breadth_snapshot",
        "核对 5 日、10 日突破比率和买盘占优标记",
    ),
    6: (
        "formula_mismatch",
        "briefing/analysis/breadth.py",
        "breadth_snapshot",
        "核对 60 日 25% 涨跌家数与差值",
    ),
    7: (
        "data_missing",
        "briefing/report/sentiment.py",
        "render_sentiment_chart",
        "核对情绪日期、看涨、看跌、横盘、多空差和图",
    ),
    9: (
        "formula_mismatch",
        "briefing/analysis/ranks.py",
        "daily_top10",
        "核对当日涨跌幅排序，以及 5/10/15/20 日 RPS 名次",
    ),
    10: (
        "formula_mismatch",
        "briefing/report/sentiment.py",
        "render_sentiment_chart",
        "核对情绪图是否只画最近两年、点数是否与窗口内的 CSV 行一致",
    ),
    11: (
        "data_missing",
        "briefing/tdx/day.py",
        "read_day_bars",
        "缺数应写缺失；通达信目录为空时应停止，不改读别的行情",
    ),
}

_SANITY = {
    "internal_identity": (
        "formula_mismatch",
        "briefing/analysis/breadth.py",
        "breadth_snapshot",
        "核对 diff25 是否等于 up25 减 down25",
    ),
    "display_rounding": (
        "formula_mismatch",
        "briefing/report/writer.py",
        "write_briefing",
        "核对展示小数与复算使用同一精度",
    ),
    "chart_point_count": (
        "data_missing",
        "briefing/report/sentiment.py",
        "render_sentiment_chart",
        "核对图的点数与 CSV 行数",
    ),
    "schema": (
        "evaluator_error",
        "briefing/evaluation/evaluator.py",
        "evaluate_briefing",
        "核对 snapshot 字段类型。这不是一条新的需求",
    ),
    "failure_isolation": (
        "evaluator_error",
        "briefing/evaluation/evaluator.py",
        "evaluate_briefing",
        "这是测试写法，不改简报数字",
    ),
}

_LIMIT = 3


def checklist_view(failure: dict) -> dict:
    """Modules and categories the checklist already names for this failure.

    ``known`` is false when a failure number or sanity name is not listed.
    The agent uses this to decide whether it still has to open a file.
    """
    categories: list[str] = []
    modules: list[str] = []
    known = True
    for number in _numbers(failure):
        row = _CHECKS.get(number)
        if row is None:
            known = False
            continue
        if row[0] not in categories:
            categories.append(row[0])
        if row[1] not in modules:
            modules.append(row[1])
    for name in _sanity(failure):
        row = _SANITY.get(name)
        if row is None:
            known = False
            continue
        if row[0] not in categories:
            categories.append(row[0])
        if row[1] not in modules:
            modules.append(row[1])
    return {"known": known, "categories": categories, "modules": modules}


def diagnose_failure(failure: dict, evidence: list[str] | None = None) -> dict:
    """Return one taxonomy classification for this failure.

    The same failure always names the same module. File text is not copied
    into the result. ``prior_fixes`` at 3 stops another diagnosis.
    """
    notes = [item for item in (evidence or []) if isinstance(item, str) and item.strip()]
    if _evaluator_crash(failure):
        return _pack(
            "STOP",
            "evaluator_error",
            "briefing/evaluation/evaluator.py",
            "evaluate_briefing",
            [_crash_note(failure), *notes],
            "检查程序抛错。这不是简报 FAIL，先修检查程序。",
            "stop",
        )
    if _only_commentary(failure) and not failure.get("commentary_rewritten"):
        return _pack(
            "FAIL",
            "commentary_violation",
            "briefing/report/commentary.py",
            "write_commentary",
            ["回到 D5，按第 8 条重写一次。此时期不诊断代码。", *notes],
            "回到 D5，按第 8 条重写一次。",
            "rewrite",
        )
    if _only_commentary(failure):
        return _pack(
            "MISSING",
            "commentary_violation",
            "briefing/report/commentary.py",
            "write_commentary",
            ["评论已重写一次，标为缺失，不再诊断。", *notes],
            "评论已重写一次，标为缺失，不再诊断。",
            "stop",
        )
    if int(failure.get("prior_fixes") or 0) >= _LIMIT:
        found = _primary(failure)
        category, module, function, look = found or (
            "formula_mismatch",
            "briefing/evaluation/evaluator.py",
            "evaluate_briefing",
            "失败项不在预定义清单里",
        )
        return _pack(
            "STOP",
            category,
            module,
            function,
            [look, *notes],
            "同一失败项已达 3 次，不再重复诊断。",
            "stop",
        )
    found = _primary(failure)
    if found is None:
        return _unlisted(failure, notes)
    category, module, function, look = found
    looks = [look]
    for extra in _secondary(failure):
        looks.append(extra[3])
    return _pack("FAIL", category, module, function, [*looks, *notes], look, "diagnose")


def _primary(failure: dict) -> tuple[str, str, str, str] | None:
    for number in _numbers(failure):
        if number in _CHECKS:
            return _CHECKS[number]
    for name in _sanity(failure):
        if name in _SANITY:
            return _SANITY[name]
    return None


def _secondary(failure: dict) -> list[tuple[str, str, str, str]]:
    found = []
    seen = False
    for number in _numbers(failure):
        row = _CHECKS.get(number)
        if row is None:
            continue
        if not seen:
            seen = True
            continue
        found.append(row)
    if _numbers(failure):
        for name in _sanity(failure):
            row = _SANITY.get(name)
            if row is not None:
                found.append(row)
        return found
    skipped = False
    for name in _sanity(failure):
        row = _SANITY.get(name)
        if row is None:
            continue
        if not skipped:
            skipped = True
            continue
        found.append(row)
    return found


def _unlisted(failure: dict, notes: list[str]) -> dict:
    blob = " ".join(notes)
    category = "data_missing" if ("缺失" in blob or "missing" in blob.lower()) else "formula_mismatch"
    module = "briefing/evaluation/evaluator.py"
    for note in notes:
        if note.startswith("已查看 briefing/"):
            module = note.removeprefix("已查看 ").strip()
            break
    return _pack(
        "FAIL",
        category,
        module,
        "evaluate_briefing",
        ["失败编号不在预定义清单里。", *notes],
        "对照已查看的模块核对这一失败，不在清单外另选文件。",
        "diagnose",
    )


def _pack(status, category, module, function, evidence, suggestion, action) -> dict:
    if category not in TAXONOMY:
        raise ValueError(category)
    return {
        "status": status,
        "failure_category": category,
        "evidence": evidence,
        "affected_module": module,
        "affected_function": function,
        "repair_suggestion": suggestion,
        "action": action,
    }


def _numbers(failure: dict) -> list[int]:
    return [number for number in (failure.get("requirement_failures") or []) if isinstance(number, int)]


def _sanity(failure: dict) -> list[str]:
    return [name for name in (failure.get("sanity_failures") or []) if isinstance(name, str)]


def _only_commentary(failure: dict) -> bool:
    return _numbers(failure) == [8] and not _sanity(failure)


def _evaluator_crash(failure: dict) -> bool:
    details = failure.get("details") or {}
    return failure.get("status") == "STOP" or "evaluator_error" in details


def _crash_note(failure: dict) -> str:
    details = failure.get("details") or {}
    note = details.get("evaluator_error")
    if isinstance(note, str) and note.strip():
        return note.strip()
    return "检查程序抛错"
