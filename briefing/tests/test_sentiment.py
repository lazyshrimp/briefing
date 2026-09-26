"""Sentiment rows store bull minus bear, and the chart keeps one point per row."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from briefing.report.sentiment import MISSING, STOP, append_sentiment, render_sentiment_chart, rows_in_window

CSV = Path(__file__).resolve().parents[1] / "data" / "sentiment.csv"


def _data_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_example_spread_is_bull_minus_bear(tmp_path: Path) -> None:
    path = tmp_path / "sentiment.csv"
    row = append_sentiment(path, "2026-09-26", 33.0, 42.0, 25.0)
    assert row["spread"] == -9.0
    stored = _data_rows(path)
    assert len(stored) == 1
    assert float(stored[0]["spread"]) == -9.0


def test_percentage_sum_outside_99_to_101_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sentiment.csv"
    assert append_sentiment(path, "2026-09-26", 33.0, 42.0, 20.0) == STOP
    assert path.is_file() is False
    assert append_sentiment(path, "2026-09-26", 33.0, 42.0, 24.0)["spread"] == -9.0
    assert append_sentiment(tmp_path / "high.csv", "2026-09-26", 34.0, 42.0, 25.0)["spread"] == -8.0


def test_an_existing_date_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sentiment.csv"
    append_sentiment(path, "2026-09-26", 33.0, 42.0, 25.0)
    assert append_sentiment(path, "2026-09-26", 40.0, 30.0, 30.0) == STOP
    assert len(_data_rows(path)) == 1
    assert float(_data_rows(path)[0]["bull"]) == 33.0


def test_chart_points_equal_data_rows_and_a_repeat_does_not_redraw(tmp_path: Path) -> None:
    path = tmp_path / "sentiment.csv"
    append_sentiment(path, "2026-09-19", 40.0, 30.0, 30.0)
    append_sentiment(path, "2026-09-26", 33.0, 42.0, 25.0)
    png = tmp_path / "sentiment.png"
    drawn = render_sentiment_chart(path, png)
    shown = rows_in_window(_data_rows(path))
    assert drawn["points"] == len(shown) == 2
    assert png.is_file()
    png.touch()
    stamped = png.stat().st_mtime_ns
    again = render_sentiment_chart(path, png)
    assert again["path"] == drawn["path"]
    assert again["points"] == 2
    assert png.stat().st_mtime_ns == stamped


def test_a_row_older_than_two_years_is_kept_but_not_drawn(tmp_path: Path) -> None:
    path = tmp_path / "sentiment.csv"
    append_sentiment(path, "2023-09-26", 40.0, 30.0, 30.0)
    append_sentiment(path, "2026-09-19", 40.0, 30.0, 30.0)
    append_sentiment(path, "2026-09-26", 33.0, 42.0, 25.0)
    drawn = render_sentiment_chart(path, tmp_path / "sentiment.png")
    stored = _data_rows(path)
    assert len(stored) == 3
    assert drawn["points"] == len(rows_in_window(stored)) == 2


def test_production_csv_window_without_drawing() -> None:
    if not CSV.is_file():
        pytest.skip("briefing/data/sentiment.csv is missing")
    stored = _data_rows(CSV)
    assert len(stored) == 229
    assert stored[0]["date"] == "2022-03-11"
    assert stored[-1]["date"] == "2026-09-18"
    window = rows_in_window(stored)
    assert window[0]["date"] == "2024-09-20"
    assert window[-1]["date"] == "2026-09-18"
    assert len(window) == 102
    by_date = {row["date"]: row for row in stored}
    assert float(by_date["2026-05-15"]["spread"]) == -11.0
    assert float(by_date["2026-06-13"]["spread"]) == 17.0
    for row in stored:
        assert float(row["spread"]) == float(row["bull"]) - float(row["bear"])


def test_empty_history_does_not_draw(tmp_path: Path) -> None:
    assert render_sentiment_chart(tmp_path / "sentiment.csv", tmp_path / "sentiment.png") == MISSING
