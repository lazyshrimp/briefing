"""Market commentary fills the draft slot. Check 8 judges the wording."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from briefing.report.commentary import write_commentary
from briefing.report.writer import assemble_draft
from briefing.tests.test_evaluator import _case, _run


def _draft():
    return assemble_draft(
        "2026-09-24",
        {
            "hs300": {"daily_buy": "YES", "weekly_buy": "NO", "above_rising_ma5": "missing"},
            "chinext": {"daily_buy": "NO", "weekly_buy": "YES", "above_rising_ma5": "NO"},
        },
        {
            "net": 7,
            "up4": 8,
            "down4": 2,
            "ratio5": {"value": 2.0, "flag": "buyers_dominate"},
            "ratio10": {"value": None, "flag": "no_down_4"},
            "up25": 5,
            "down25": 2,
            "diff25": 3,
        },
        {
            "hs300": {"above": 1, "total": 4, "pct": 0.25},
            "chinext": "missing",
            "all_a": {"above": 1, "total": 8, "pct": 0.125},
        },
        {
            "daily": {
                "industry": {"items": [{"name": "甲", "code": "880001", "pct": 0.1}]},
                "concept": {"items": []},
            },
            "rps": {"industry": {}, "concept": {}},
        },
        {"date": "2026-09-18", "bull": 33.0, "bear": 42.0, "flat": 25.0, "spread": -9.0, "chart": "x.png"},
    )


def _frozen(draft):
    return copy.deepcopy(draft.snapshot), copy.deepcopy(draft.sentiment)


def test_an_unconfigured_model_marks_commentary_missing_without_changing_numbers() -> None:
    draft = _draft()
    snapshot, sentiment = _frozen(draft)
    called = False

    def judge(text, metrics):
        nonlocal called
        called = True
        return None

    result = write_commentary(draft, judge=judge)
    assert result.is_missing()
    assert result.metrics_used == []
    assert draft.commentary is result
    assert draft.snapshot == snapshot
    assert draft.sentiment == sentiment
    assert called is False


def test_a_timeout_marks_commentary_missing_without_changing_numbers() -> None:
    draft = _draft()
    snapshot, sentiment = _frozen(draft)

    def complete(prompt):
        raise TimeoutError("timeout")

    result = write_commentary(draft, complete=complete)
    assert result.is_missing()
    assert result.metrics_used == []
    assert draft.snapshot == snapshot
    assert draft.sentiment == sentiment


def test_a_bad_payload_is_missing_without_a_rewrite() -> None:
    calls = []

    def complete(prompt):
        calls.append(prompt)
        return {"text": ""}

    def judge(text, metrics):
        raise AssertionError("an unusable payload is not sent to the evaluator")

    result = write_commentary(_draft(), complete=complete, judge=judge)
    assert result.is_missing()
    assert result.metrics_used == []
    assert len(calls) == 1


def test_the_prompt_lists_missing_items_apart_from_usable_metrics() -> None:
    seen = []

    def complete(prompt):
        seen.append(prompt)
        return {"text": "净值为正。", "metrics_used": ["net"]}

    draft = _draft()
    snapshot, sentiment = _frozen(draft)
    result = write_commentary(draft, complete=complete)
    prompt = seen[0]
    usable, _, missing = prompt.partition("缺失项：")
    assert "net=7" in usable
    assert "hs300.above_rising_ma5" not in usable
    assert "hs300.above_rising_ma5" in missing
    assert "禁止编造市场数据" in prompt
    assert "买入或卖出建议" in prompt
    assert "仓位建议" in prompt
    assert "缺失项不得写成结论" in prompt
    assert result.text == "净值为正。"
    assert result.metrics_used == ["net"]
    assert draft.snapshot == snapshot
    assert draft.sentiment == sentiment


def test_a_json_string_payload_is_accepted() -> None:
    def complete(prompt):
        return json.dumps({"text": "净值为正。", "metrics_used": ["net"]}, ensure_ascii=False)

    result = write_commentary(_draft(), complete=complete)
    assert result.text == "净值为正。"
    assert result.metrics_used == ["net"]


def test_write_commentary_does_not_create_a_markdown_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_commentary(_draft(), complete=lambda prompt: {"text": "净值为正。", "metrics_used": ["net"]})
    assert list(tmp_path.rglob("*.md")) == []
    source = Path(__file__).resolve().parents[1].joinpath("report", "commentary.py").read_text(encoding="utf-8")
    assert "write_briefing" not in source


def test_one_rejection_is_rewritten_once() -> None:
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            return {"text": "建议买入", "metrics_used": ["net"]}
        return {"text": "5日买盘占优。", "metrics_used": ["net"]}

    def judge(text, metrics):
        if "买入" in text:
            return "评论含有买入建议"
        return None

    draft = _draft()
    snapshot, _sentiment = _frozen(draft)
    result = write_commentary(draft, complete=complete, judge=judge)
    assert len(prompts) == 2
    assert "上次未通过的原因" not in prompts[0]
    assert "评论含有买入建议" in prompts[1]
    assert result.text == "5日买盘占优。"
    assert result.metrics_used == ["net"]
    assert draft.snapshot == snapshot


def test_a_second_rejection_marks_commentary_missing() -> None:
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        return {"text": "建议买入", "metrics_used": ["net"]}

    def judge(text, metrics):
        if "买入" in text:
            return "评论含有买入建议"
        return None

    draft = _draft()
    snapshot, sentiment = _frozen(draft)
    result = write_commentary(draft, complete=complete, judge=judge)
    assert len(prompts) == 2
    assert "评论含有买入建议" in prompts[1]
    assert result.is_missing()
    assert result.metrics_used == []
    assert draft.commentary is result
    assert draft.snapshot == snapshot
    assert draft.sentiment == sentiment


def _comment(tmp_path: Path, text: str, metrics: list[str]):
    path, snapshot, reference, context = _case(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("评论桩", text, 1), encoding="utf-8")
    context["metrics_used"] = metrics
    return _run(path, snapshot, reference, context)


def test_dates_periods_and_percentages_do_not_fail_check_8(tmp_path: Path) -> None:
    text = "2026-09-24 的 5日、10日、60日 买盘占优，涨跌幅 8.17%，净值 7 点。编号 12345。"
    result = _comment(tmp_path, text, ["net", "甲"])
    assert result["requirement_failures"] == []
    assert result["not_checked"] == []
    assert result["status"] == "PASS"


def test_buy_advice_fails_check_8(tmp_path: Path) -> None:
    result = _comment(tmp_path, "建议买入", ["net"])
    assert result["requirement_failures"] == [8]
    assert "买入" in result["details"][8]


def test_a_price_fails_check_8(tmp_path: Path) -> None:
    result = _comment(tmp_path, "目标价 12.5元", ["net"])
    assert result["requirement_failures"] == [8]
    assert "价格" in result["details"][8]


def test_a_position_fails_check_8(tmp_path: Path) -> None:
    result = _comment(tmp_path, "仓位保持半仓", ["net"])
    assert result["requirement_failures"] == [8]
    assert "仓位" in result["details"][8]


def test_an_index_level_outside_the_snapshot_fails_check_8(tmp_path: Path) -> None:
    result = _comment(tmp_path, "沪深300收在 3250 点", ["net"])
    assert result["requirement_failures"] == [8]
    assert "3250" in result["details"][8]


def test_an_unknown_metric_fails_check_8(tmp_path: Path) -> None:
    result = _comment(tmp_path, "评论桩", ["not_a_metric"])
    assert result["requirement_failures"] == [8]
    assert result["details"][8].startswith("metrics_used 含 snapshot 之外的指标：")


def test_a_missing_commentary_passes_check_8(tmp_path: Path) -> None:
    result = _comment(tmp_path, "缺失", [])
    assert result["requirement_failures"] == []
    assert result["status"] == "PASS"


def test_check_8_stays_unchecked_without_metrics_used(tmp_path: Path) -> None:
    path, snapshot, reference, context = _case(tmp_path)
    context.pop("metrics_used")
    result = _run(path, snapshot, reference, context)
    assert 8 not in result["requirement_failures"]
    assert result["not_checked"] == [8]
    assert result["status"] != "PASS"
