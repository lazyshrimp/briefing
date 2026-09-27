"""Development step 2: the code map is a document, not a skill."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CODE_MAP = ROOT / "briefing" / "output" / "code-map.md"
TDX = Path(r"C:\zd_pazq_hy")


def _rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line or "处置" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def test_the_code_map_has_eleven_rows_and_marks_stockbee_unusable() -> None:
    if not TDX.is_dir():
        pytest.fail("通达信目录不存在，停止")
    text = CODE_MAP.read_text(encoding="utf-8")
    rows = _rows(text)
    assert len(rows) == 11
    stockbee = [row for row in rows if "Stockbee" in row[0] and "25%" in row[0]]
    assert len(stockbee) == 1
    assert stockbee[0][2] == "不可复用"
    for row in rows:
        if row is stockbee[0]:
            continue
        assert row[2] in {"copy", "new"}
    assert not (ROOT / "briefing" / "skills" / "code_understanding.py").exists()
