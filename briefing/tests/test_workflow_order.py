"""The daily run calls D1 through D7 in order and writes the markdown once."""

from __future__ import annotations

import struct
from pathlib import Path

from briefing.core.models import Commentary, Snapshot
from briefing.skills import compute_snapshot as snapshot_module
from briefing.skills.compute_snapshot import compute_snapshot
from briefing.workflow import daily

ON = "2026-09-24"
ORDER = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]


def _snapshot() -> Snapshot:
    return Snapshot(
        on_date=ON,
        signals={
            "hs300": {"daily_buy": "YES", "weekly_buy": "NO", "above_rising_ma5": "YES"},
            "chinext": {"daily_buy": "NO", "weekly_buy": "NO", "above_rising_ma5": "NO"},
        },
        breadth={
            "net": 7,
            "up4": 1,
            "down4": 1,
            "ratio5": {"value": 1.0, "flag": None},
            "ratio10": {"value": None, "flag": "no_down_4"},
            "up25": 1,
            "down25": 1,
            "diff25": 0,
        },
        ma50={"hs300": "missing", "chinext": "missing", "all_a": "missing"},
        ranks="missing",
    )


def _loaded() -> dict:
    return {
        "sentiment": "missing",
        "chart_redrawn": False,
        "new_sentiment_week": False,
        "chart_points": 0,
    }


def _index(root: Path, dates: list[int]) -> None:
    path = root / "vipdoc" / "sh" / "lday" / "sh000300.day"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"".join(struct.pack("<IIIIIfII", day, 100, 100, 100, 100, 0.0, 1, 0) for day in dates))


def _install(monkeypatch, log: list[str], output: Path, *, evaluation: dict | None = None) -> None:
    monkeypatch.setattr(daily, "d1_calendar", lambda on_date, tdx_dir: log.append("D1") or "trading_day")
    monkeypatch.setattr(daily, "d2_read", lambda on_date, tdx_dir: log.append("D2") or {"on_date": on_date})
    monkeypatch.setattr(daily, "d3_compute", lambda raw: log.append("D3") or _snapshot())
    monkeypatch.setattr(daily, "d4_sentiment", lambda csv_path, png_path, tdx_dir: log.append("D4") or _loaded())

    def d5(draft, complete=None):
        log.append("D5")
        assert not (output / f"{ON}.md").exists()
        draft.commentary = Commentary(text="净值为正。", metrics_used=["net"])
        return draft.commentary

    def d6(draft, output_dir):
        log.append("D6")
        path = Path(output_dir) / f"{draft.snapshot.on_date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(draft.commentary.text, encoding="utf-8")
        return {"path": str(path)}

    def d7(path, draft, context):
        log.append("D7")
        return evaluation or {"status": "PASS", "requirement_failures": [], "sanity_failures": [], "not_checked": []}

    monkeypatch.setattr(daily, "d5_commentary", d5)
    monkeypatch.setattr(daily, "d6_write", d6)
    monkeypatch.setattr(daily, "d7_evaluate", d7)


def test_progress_names_each_step_before_it_runs(tmp_path: Path, monkeypatch) -> None:
    log: list[str] = []
    notes: list[str] = []
    output = tmp_path / "output"
    _install(monkeypatch, log, output)
    daily.run_daily(ON, tdx_dir=tmp_path, output_dir=output, progress=notes.append)
    assert [note.split()[0] for note in notes] == ORDER
    assert any("全市场" in note for note in notes)
    assert any("再扫一次" in note for note in notes)


def test_stubs_record_d1_through_d7_and_skip_the_spec(tmp_path: Path, monkeypatch) -> None:
    log: list[str] = []
    output = tmp_path / "output"
    _install(monkeypatch, log, output)
    result = daily.run_daily(
        ON,
        tdx_dir=tmp_path,
        output_dir=output,
        complete=lambda prompt: {"text": "不会用到", "metrics_used": ["net"]},
    )
    assert log == ORDER
    assert result["steps"] == ORDER
    assert result["status"] == "PASS"
    assert result["completed"] is True
    assert result["candidate"] is False
    assert "read_requirement" not in log
    source = Path(daily.__file__).read_text(encoding="utf-8")
    assert "read_requirement" not in source
    assert "requirement-analysis" not in source
    assert "diagnose" not in source


def test_a_gap_inside_the_calendar_skips_without_a_file(tmp_path: Path, monkeypatch) -> None:
    _index(tmp_path, [20260918, 20260922])
    called = []
    monkeypatch.setattr(daily, "d2_read", lambda on_date, tdx_dir: called.append("D2"))
    output = tmp_path / "output"
    result = daily.run_daily("2026-09-21", tdx_dir=tmp_path, output_dir=output)
    assert result["status"] == "SKIP"
    assert result["steps"] == ["D1"]
    assert called == []
    assert list(output.glob("*.md")) == []


def test_a_target_after_the_last_bar_stops(tmp_path: Path, monkeypatch) -> None:
    _index(tmp_path, [20260922])
    called = []
    monkeypatch.setattr(daily, "d2_read", lambda on_date, tdx_dir: called.append("D2"))
    result = daily.run_daily("2026-09-26", tdx_dir=tmp_path, output_dir=tmp_path / "output")
    assert result["status"] == "STOP"
    assert result["steps"] == ["D1"]
    assert called == []


def test_a_stop_in_d2_does_not_call_later_steps(tmp_path: Path, monkeypatch) -> None:
    called = []
    monkeypatch.setattr(daily, "d1_calendar", lambda on_date, tdx_dir: "trading_day")
    monkeypatch.setattr(daily, "d3_compute", lambda raw: called.append("D3"))
    output = tmp_path / "output"
    result = daily.run_daily(ON, tdx_dir=tmp_path, output_dir=output)
    assert result["status"] == "STOP"
    assert result["steps"] == ["D1", "D2"]
    assert called == []
    assert list(output.glob("*.md")) == []


def test_a_rejected_commentary_is_still_written_once_as_missing(tmp_path: Path, monkeypatch) -> None:
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        return {"text": "建议买入", "metrics_used": ["net"]}

    monkeypatch.setattr(daily, "d1_calendar", lambda on_date, tdx_dir: "trading_day")
    monkeypatch.setattr(daily, "d2_read", lambda on_date, tdx_dir: {"on_date": on_date})
    monkeypatch.setattr(daily, "d3_compute", lambda raw: _snapshot())
    monkeypatch.setattr(daily, "d4_sentiment", lambda csv_path, png_path, tdx_dir: _loaded())
    monkeypatch.setattr(
        daily,
        "d7_evaluate",
        lambda path, draft, context: {
            "status": "PASS",
            "requirement_failures": [],
            "sanity_failures": [],
            "not_checked": [],
        },
    )
    output = tmp_path / "output"
    result = daily.run_daily(ON, tdx_dir=tmp_path, output_dir=output, complete=complete)
    text = Path(result["path"]).read_text(encoding="utf-8")
    commentary = text.split("\n## 市场评论\n", 1)[1].split("\n## ", 1)[0].strip()
    assert commentary == "缺失"
    assert "建议买入" not in text
    assert len(prompts) == 2
    assert result["steps"].count("D6") == 1
    assert list(output.glob("*.md")) == [output / f"{ON}.md"]


def test_a_second_run_overwrites_the_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(daily, "d1_calendar", lambda on_date, tdx_dir: "trading_day")
    monkeypatch.setattr(daily, "d2_read", lambda on_date, tdx_dir: {"on_date": on_date})
    monkeypatch.setattr(daily, "d3_compute", lambda raw: _snapshot())
    monkeypatch.setattr(daily, "d4_sentiment", lambda csv_path, png_path, tdx_dir: _loaded())
    monkeypatch.setattr(
        daily,
        "d7_evaluate",
        lambda path, draft, context: {
            "status": "FAIL",
            "requirement_failures": [4],
            "sanity_failures": [],
            "not_checked": [],
        },
    )
    output = tmp_path / "output"
    output.mkdir()
    existing = output / f"{ON}.md"
    existing.write_text("OLD CANDIDATE", encoding="utf-8")

    first = daily.run_daily(
        ON,
        tdx_dir=tmp_path,
        output_dir=output,
        complete=lambda prompt: {"text": "净值为正。", "metrics_used": ["net"]},
    )
    assert first["candidate"] is True
    assert first["completed"] is False
    assert first["steps"] == ORDER
    body = existing.read_text(encoding="utf-8")
    assert "OLD CANDIDATE" not in body
    assert "净值为正。" in body

    second = daily.run_daily(
        ON,
        tdx_dir=tmp_path,
        output_dir=output,
        complete=lambda prompt: {"text": "第二次覆盖。", "metrics_used": ["net"]},
    )
    assert list(output.glob("*.md")) == [existing]
    assert list(output.glob(f".{ON}.md.tmp")) == []
    assert "第二次覆盖。" in existing.read_text(encoding="utf-8")
    assert "净值为正。" not in existing.read_text(encoding="utf-8")
    assert second["path"] == first["path"]


def test_compute_snapshot_keeps_the_supplied_net(tmp_path: Path) -> None:
    raw = {
        "on_date": ON,
        "hs300_bars": [{"date": ON, "close": 1.0, "volume": 1}],
        "chinext_bars": "missing",
        "trading_dates": [ON],
        "universe": [],
        "read_failures": 1,
        "new_high_net": 7,
        "hs300_above": "missing",
        "chinext_above": "missing",
        "all_a_above": "missing",
        "denominators": "missing",
        "groups": "stop",
        "lday_dir": tmp_path,
        "extdata_dir": tmp_path,
    }
    snapshot = compute_snapshot(raw)
    assert isinstance(snapshot, Snapshot)
    assert snapshot.breadth["net"] == 7
    assert snapshot.breadth["up4"] == "missing"
    assert snapshot.signals["chinext"]["daily_buy"] == "missing"
    assert snapshot.ranks == "missing"
    raw["hs300_bars"] = [{"date": "2026-09-23", "close": 1.0, "volume": 1}]
    assert compute_snapshot(raw) == "stop"
    source = Path(snapshot_module.__file__).read_text(encoding="utf-8")
    assert "requirement-analysis" not in source
