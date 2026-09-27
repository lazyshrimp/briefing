"""The facts commentary only restates metrics the prompt already lists."""

from __future__ import annotations

from briefing.evaluation.evaluator import commentary_rejection
from briefing.report.commentary import write_commentary
from briefing.report.facts_commentary import complete_from_prompt
from briefing.tests.test_commentary import _draft


def _snapshot(draft) -> dict:
    return {
        "signals": draft.snapshot.signals,
        "breadth": draft.snapshot.breadth,
        "ma50": draft.snapshot.ma50,
        "ranks": draft.snapshot.ranks,
        "sentiment": draft.sentiment,
    }


def test_facts_commentary_passes_check_8_and_avoids_trade_advice() -> None:
    draft = _draft()
    snapshot = _snapshot(draft)

    def judge(text, metrics):
        return commentary_rejection(text, metrics, snapshot)

    result = write_commentary(draft, complete=complete_from_prompt, judge=judge)
    assert not result.is_missing()
    assert "买入" not in result.text
    assert "卖出" not in result.text
    assert "仓位" not in result.text
    assert "甲" in result.text
    assert "net" in result.metrics_used
    assert "甲" in result.metrics_used
    assert commentary_rejection(result.text, result.metrics_used, snapshot) is None


def test_a_repeated_name_keeps_the_first_value_and_ratios_use_two_decimals() -> None:
    repeated = complete_from_prompt("可用指标：\n- 甲=0.0817\n- 甲=0.217\n\n缺失项：\n")
    assert "8.17%" in repeated["text"]
    assert "21.70%" not in repeated["text"]
    ratio = complete_from_prompt("可用指标：\n- ratio5=2.354235423542354 买盘占优\n\n缺失项：\n")
    assert "2.35 买盘占优" in ratio["text"]
    assert "2.354" not in ratio["text"]
    glossed = complete_from_prompt("可用指标：\n- net=7（52周新高家数减去新低家数）\n\n缺失项：\n")
    assert "52周新高减新低为 7。" in glossed["text"]
    assert "减去新低" not in glossed["text"]
