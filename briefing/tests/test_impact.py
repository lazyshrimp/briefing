"""Development step 3: the impact note stays inside the briefing boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPACT = ROOT / "briefing" / "output" / "impact.md"


def test_the_impact_note_does_not_change_the_spec_or_the_data_source() -> None:
    text = IMPACT.read_text(encoding="utf-8")
    assert "修改需求" not in text
    assert "更换行情源" not in text
    assert "briefing/" in text
    assert r"C:\zd_pazq_hy" in text
    assert "仓位" in text
    assert not (ROOT / "briefing" / "skills" / "impact.py").exists()
