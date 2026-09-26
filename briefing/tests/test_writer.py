"""The day's markdown is written only after the commentary slot is filled."""

from __future__ import annotations

import re
from pathlib import Path

from briefing.analysis.breadth import BUYERS_DOMINATE, NO_DOWN_4
from briefing.core.models import Commentary, missing_commentary
from briefing.report.writer import SECTIONS, STOP, assemble_draft, write_briefing

ON = "2026-09-24"
STUB = "今天只复述已经算好的数字。"


def _draft():
    return assemble_draft(
        ON,
        signals={
            "hs300": {"daily_buy": "YES", "weekly_buy": "NO", "above_rising_ma5": "YES"},
            "chinext": {"daily_buy": "NO", "weekly_buy": "YES", "above_rising_ma5": "missing"},
        },
        breadth={
            "net": -71,
            "up4": 140,
            "down4": 494,
            "ratio5": {"value": 2.35, "flag": BUYERS_DOMINATE},
            "ratio10": {"value": None, "flag": NO_DOWN_4},
            "up25": 327,
            "down25": 623,
            "diff25": -296,
        },
        ma50={
            "hs300": {"above": 80, "total": 300, "pct": 80 / 300},
            "chinext": "missing",
            "all_a": {"above": 2896, "total": 5227, "pct": 2896 / 5227},
        },
        ranks={
            "daily": {
                "industry": {"items": [{"name": "林业", "code": "880363", "pct": 0.0817}]},
                "concept": {"items": [{"name": "风沙治理", "code": "880585", "pct": "missing"}], "flag": "short_list"},
            },
            "rps": {
                "industry": {5: {"items": [{"name": "红黄酒", "code": "880383", "pct": 0.2309, "rps": 1000}]}},
                "concept": {},
            },
        },
        sentiment={
            "date": "2026-09-18",
            "bull": 33.0,
            "bear": 42.0,
            "flat": 25.0,
            "spread": -9.0,
            "chart": "briefing/data/sentiment.png",
        },
    )


def _section(text: str, title: str) -> str:
    body = text.split(f"\n## {title}\n", maxsplit=1)[1]
    following = body.find("\n## ")
    if following >= 0:
        body = body[:following]
    return body.strip()


def test_an_empty_commentary_slot_does_not_write_the_day_file(tmp_path: Path) -> None:
    draft = _draft()
    assert draft.commentary is None
    assert write_briefing(draft, tmp_path) == STOP
    assert list(tmp_path.glob("*.md")) == []
    assert list(tmp_path.glob("*.tmp")) == []
    assert not (tmp_path / f"{ON}.md").exists()


def test_a_commentary_stub_writes_all_five_sections_at_once(tmp_path: Path) -> None:
    draft = _draft()
    draft.commentary = Commentary(text=STUB, metrics_used=["net"])
    written = write_briefing(draft, tmp_path)
    path = tmp_path / f"{ON}.md"
    assert written["path"] == str(path)
    assert path.is_file()
    assert ON in path.name
    text = path.read_text(encoding="utf-8")
    for title in SECTIONS:
        assert text.count(f"## {title}") == 1
    assert _section(text, "市场评论") == STUB
    assert "Daily Buy Signal：YES" in text
    assert "Price Action Above Rising 5-DMA：缺失" in text
    assert "52周新高减新低：-71" in text
    assert "沪深300 50日线以上比例：26.67%（80 / 300）" in text
    assert "沪深 50日线以上比例：55.40%（2896 / 5227）" in text
    assert "创业板 50日线以上比例：缺失" in text
    assert "当日4%+涨/跌家数：140 / 494" in text
    assert "4%突破比率（5日）：2.35 买盘占优" in text
    assert "4%突破比率（10日）：无跌幅≥4%" in text
    assert "滚动60日涨/跌25%家数：327 / 623" in text
    assert "60日25%多空差：-296" in _section(text, "广度")
    assert [line for line in text.splitlines() if line.startswith("- 多空差：")] == ["- 多空差：-9.0%"]
    assert "- 多空差：-9.0%" in _section(text, "投资者情绪")
    assert "看涨：33.0%" in text
    assert "看跌：42.0%" in text
    assert "横盘：25.0%" in text
    assert "1. 林业 8.17%" in text
    assert "1. 风沙治理 缺失" in text
    assert "（不足 10 个）" in text
    assert "short_list" not in text
    assert "1. 红黄酒 23.09% RPS 1000" in text
    assert list(tmp_path.glob("*.tmp")) == []


def test_chart_link_resolves_from_the_markdown_directory(tmp_path: Path) -> None:
    png = tmp_path / "charts" / "sentiment.png"
    png.parent.mkdir()
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    output = tmp_path / "output"
    draft = _draft()
    draft.sentiment["chart"] = str(png)
    draft.commentary = Commentary(text=STUB, metrics_used=["net"])
    write_briefing(draft, output)
    markdown = output / f"{ON}.md"
    match = re.search(r"!\[\]\(([^)]+)\)", markdown.read_text(encoding="utf-8"))
    assert match is not None
    href = match.group(1)
    assert "\\" not in href
    resolved = (markdown.parent / href).resolve()
    assert resolved == png.resolve()
    assert resolved.is_file()


def test_a_cross_drive_chart_link_uses_a_file_uri(tmp_path: Path, monkeypatch) -> None:
    png = tmp_path / "sentiment.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    draft = _draft()
    draft.sentiment["chart"] = str(png)
    draft.commentary = Commentary(text=STUB, metrics_used=["net"])

    def different_drive(path, start):
        raise ValueError("paths are on different drives")

    monkeypatch.setattr("briefing.report.writer.os.path.relpath", different_drive)
    output = tmp_path / "output"
    write_briefing(draft, output)
    match = re.search(r"!\[\]\(([^)]+)\)", (output / f"{ON}.md").read_text(encoding="utf-8"))
    assert match is not None
    assert match.group(1) == png.as_uri()


def test_a_missing_commentary_is_written_as_缺失(tmp_path: Path) -> None:
    draft = _draft()
    draft.commentary = missing_commentary()
    assert write_briefing(draft, tmp_path)["path"].endswith(f"{ON}.md")
    text = (tmp_path / f"{ON}.md").read_text(encoding="utf-8")
    assert _section(text, "市场评论") == "缺失"
    assert "52周新高减新低：-71" in text


def test_missing_sentiment_stays_inside_its_section(tmp_path: Path) -> None:
    draft = _draft()
    draft.sentiment = "missing"
    draft.commentary = Commentary(text=STUB, metrics_used=[])
    write_briefing(draft, tmp_path)
    text = (tmp_path / f"{ON}.md").read_text(encoding="utf-8")
    assert _section(text, "投资者情绪") == "缺失"
    assert _section(text, "市场评论") == STUB


def test_a_second_write_replaces_the_same_file(tmp_path: Path) -> None:
    draft = _draft()
    draft.commentary = Commentary(text="第一稿", metrics_used=["net"])
    write_briefing(draft, tmp_path)
    draft.commentary = Commentary(text="第二稿", metrics_used=["net"])
    write_briefing(draft, tmp_path)
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    assert files[0].name == f"{ON}.md"
    assert _section(files[0].read_text(encoding="utf-8"), "市场评论") == "第二稿"


def test_a_failed_write_does_not_leave_the_day_file(tmp_path: Path, monkeypatch) -> None:
    draft = _draft()
    draft.commentary = Commentary(text=STUB, metrics_used=["net"])

    def fail_replace(source, target):
        raise OSError("rename failed")

    monkeypatch.setattr("briefing.report.writer.os.replace", fail_replace)
    assert write_briefing(draft, tmp_path) == STOP
    assert not (tmp_path / f"{ON}.md").exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob("*.md")) == []
