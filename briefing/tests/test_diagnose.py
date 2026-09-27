"""The same failure always names the same module, and diagnosis does not edit files."""

from __future__ import annotations

import subprocess
from pathlib import Path

from briefing.agents.diagnostic import diagnose
from briefing.skills.diagnose import TAXONOMY, diagnose_failure

ROOT = Path(__file__).resolve().parents[2]


def _failure(numbers: list[int], **extra) -> dict:
    payload = {
        "status": "FAIL",
        "requirement_failures": numbers,
        "sanity_failures": [],
        "details": {},
    }
    payload.update(extra)
    return payload


def test_the_same_breadth_failure_always_names_breadth() -> None:
    failure = _failure([4])
    first = diagnose_failure(failure)
    second = diagnose_failure(failure)
    assert first == second
    assert first["failure_category"] == "formula_mismatch"
    assert first["failure_category"] in TAXONOMY
    assert first["affected_module"] == "briefing/analysis/breadth.py"
    assert first["affected_function"] == "breadth_snapshot"
    assert "def breadth_snapshot" not in " ".join(first["evidence"])


def test_check_8_rewrites_once_and_then_stops_diagnosing() -> None:
    pending = diagnose_failure(_failure([8], commentary_rewritten=False))
    assert pending["action"] == "rewrite"
    assert pending["failure_category"] == "commentary_violation"
    assert pending["affected_module"] == "briefing/report/commentary.py"
    done = diagnose_failure(_failure([8], commentary_rewritten=True))
    assert done["status"] == "MISSING"
    assert "不再诊断" in done["repair_suggestion"]


def test_three_fixes_stop_another_diagnosis() -> None:
    result = diagnose_failure(_failure([6], prior_fixes=3))
    assert result["status"] == "STOP"
    assert result["affected_module"] == "briefing/analysis/breadth.py"
    assert "不再重复诊断" in result["repair_suggestion"]


def test_an_evaluator_crash_is_not_a_briefing_failure() -> None:
    result = diagnose_failure(
        {
            "status": "STOP",
            "requirement_failures": [],
            "sanity_failures": [],
            "details": {"evaluator_error": "RuntimeError: boom"},
        }
    )
    assert result["failure_category"] == "evaluator_error"
    assert result["status"] == "STOP"
    assert result["affected_module"] == "briefing/evaluation/evaluator.py"


def test_a_listed_failure_does_not_open_files() -> None:
    calls: list[str] = []

    def tool(name):
        def _run(*_args, **_kwargs):
            calls.append(name)
            return ""

        return _run

    result = diagnose(_failure([2]), tools={key: tool(key) for key in ("read_file", "search_code", "git_diff", "git_status")})
    assert calls == []
    assert result["affected_module"] == "briefing/analysis/signals.py"
    assert result["affected_files"] == ["briefing/analysis/signals.py"]
    assert result["affected_functions"] == ["index_signals"]


def test_two_categories_ask_the_agent_to_read_before_the_skill_decides() -> None:
    calls: list[str] = []

    def tool(name):
        def _run(*_args, **_kwargs):
            calls.append(name)
            return ""

        return _run

    result = diagnose(
        _failure([2, 7]),
        tools={key: tool(key) for key in ("read_file", "search_code", "git_diff", "git_status")},
    )
    assert calls[:2] == ["git_status", "git_diff"]
    assert calls.count("read_file") == 2
    assert "search_code" in calls
    assert result["failure_category"] == "formula_mismatch"
    assert result["affected_module"] == "briefing/analysis/signals.py"
    assert "briefing/report/sentiment.py" in result["affected_files"]
    assert "def index_signals" not in " ".join(result["evidence"])


def test_diagnosis_does_not_change_the_worktree() -> None:
    before = _porcelain()
    diagnose(_failure([4, 11]))
    assert _porcelain() == before
    for name in ("code_understanding.py", "impact.py", "review.py"):
        assert not (ROOT / "briefing" / "skills" / name).exists()


def _porcelain() -> str:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout
