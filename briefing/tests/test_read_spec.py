"""Development step 1: the spec is read and left unchanged."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "notes" / "skills" / "requirement-analysis.md"


def test_the_spec_is_readable_and_the_daily_workflow_does_not_open_it() -> None:
    before = SPEC.read_bytes()
    text = SPEC.read_text(encoding="utf-8")
    assert "验收标准" in text
    assert SPEC.read_bytes() == before
    daily = (ROOT / "briefing" / "workflow" / "daily.py").read_text(encoding="utf-8")
    assert "requirement-analysis" not in daily
    assert "read_requirement" not in daily
