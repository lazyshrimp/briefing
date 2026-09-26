"""Append one week of sentiment and draw the two-panel sentiment chart.

The spread is bull minus bear. The picture follows the canslim layout:
深证综指 on top, the spread underneath, for the latest two years.
A week already stored is not written again, and a chart already drawn
for that last date is not drawn again.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from briefing.tdx.day import read_day_bars

MISSING = "missing"
STOP = "stop"
_FIELDS = ("date", "bull", "bear", "flat", "spread")
_LOOKBACK_YEARS = 2
_BUY_LINE = -22.5
_SELL_LINE = 52.5
_DEFAULT_TDX = Path(r"C:\zd_pazq_hy")


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def append_sentiment(
    csv_path: str | Path,
    on_date: str,
    bull: float,
    bear: float,
    flat: float,
) -> dict | str:
    """Append one week. The three percentages must sum to 99–101."""
    path = Path(csv_path)
    total = float(bull) + float(bear) + float(flat)
    if total < 99 or total > 101:
        return STOP
    rows = _rows(path)
    if any(row["date"] == on_date for row in rows):
        return STOP
    row = {
        "date": on_date,
        "bull": float(bull),
        "bear": float(bear),
        "flat": float(flat),
        "spread": float(bull) - float(bear),
    }
    rows.append(row)
    _write(path, rows)
    return row


def _cutoff(latest: date) -> date:
    try:
        return latest.replace(year=latest.year - _LOOKBACK_YEARS)
    except ValueError:
        return latest.replace(year=latest.year - _LOOKBACK_YEARS, day=28)


def rows_in_window(rows: list[dict]) -> list[dict]:
    """Rows from two years before the last date through that date, inclusive."""
    if not rows:
        return []
    latest = date.fromisoformat(rows[-1]["date"])
    start = _cutoff(latest)
    return [row for row in rows if date.fromisoformat(row["date"]) >= start]


def render_sentiment_chart(
    csv_path: str | Path,
    png_path: str | Path,
    tdx_dir: str | Path = _DEFAULT_TDX,
) -> dict | str:
    """Draw the latest two years. An unchanged last date keeps the old file."""
    path = Path(csv_path)
    rows = _rows(path)
    if not rows:
        return MISSING
    shown = rows_in_window(rows)
    target = Path(png_path)
    stamp = target.with_suffix(".stamp")
    last = rows[-1]["date"]
    if target.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == last:
        return {"path": str(target), "points": len(shown)}
    _draw(shown, target, Path(tdx_dir))
    stamp.write_text(last, encoding="utf-8")
    return {"path": str(target), "points": len(shown)}


def _index_closes(tdx_dir: Path, start: date, end: date) -> tuple[list[date], list[float]]:
    bars = read_day_bars(tdx_dir / "vipdoc" / "sz" / "lday" / "sz399106.day")
    if not isinstance(bars, list):
        return [], []
    dates: list[date] = []
    closes: list[float] = []
    for bar in bars:
        day = date.fromisoformat(bar["date"])
        if start <= day <= end:
            dates.append(day)
            closes.append(float(bar["close"]))
    return dates, closes


def _draw(rows: list[dict], target: Path, tdx_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    sent_dates = [date.fromisoformat(row["date"]) for row in rows]
    spread = [float(row["spread"]) for row in rows]
    idx_dates, idx_closes = _index_closes(tdx_dir, sent_dates[0], sent_dates[-1])

    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "PingFang SC", "sans-serif"],
            "axes.unicode_minus": False,
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#fafbfc",
            "axes.edgecolor": "#cccccc",
            "axes.grid": True,
            "grid.color": "#eeeeee",
            "grid.linewidth": 0.6,
        }
    )
    fig, (ax_top, ax_bot) = plt.subplots(
        2,
        1,
        figsize=(16, 9),
        dpi=150,
        sharex=True,
        gridspec_kw={"height_ratios": [1.1, 1], "hspace": 0.22},
        layout="constrained",
    )

    if idx_dates:
        low = min(idx_closes)
        high = max(idx_closes)
        pad = (high - low) * 0.08 or 1.0
        floor = low - pad
        ax_top.set_ylim(floor, high + pad)
        ax_top.fill_between(idx_dates, idx_closes, floor, alpha=0.15, color="#4da3ff")
        ax_top.plot(idx_dates, idx_closes, color="#4da3ff", linewidth=1.8, label="深证综指")
        ax_top.set_title(
            f"投资者情绪图  ({idx_dates[0]} ~ {idx_dates[-1]})",
            fontsize=15,
            fontweight="bold",
            pad=10,
            color="#1a1a2e",
        )
    else:
        ax_top.set_title("投资者情绪图", fontsize=15, fontweight="bold", pad=10, color="#1a1a2e")
    ax_top.set_ylabel("深证综指", fontsize=11, color="#4da3ff", fontweight="bold")
    ax_top.yaxis.set_tick_params(labelsize=9)
    ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_top.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax_top.xaxis.set_minor_locator(mdates.MonthLocator())
    ax_top.tick_params(axis="x", labelsize=8, rotation=30)
    if idx_dates:
        ax_top.legend(loc="upper left", fontsize=9, framealpha=0.8)
    ax_top_r = ax_top.twinx()
    ax_top_r.set_ylim(ax_top.get_ylim())
    ax_top_r.yaxis.set_tick_params(labelsize=9)
    ax_top_r.set_ylabel("")

    ax_bot.plot(
        sent_dates,
        spread,
        color="#e67e22",
        linewidth=1.6,
        linestyle="--",
        marker="^",
        markersize=3,
        label="多空差 %",
    )
    ax_bot.axhline(y=0, color="#bbb", linewidth=0.8, linestyle="-")
    ax_bot.axhline(y=_BUY_LINE, color="#4CAF50", linestyle="--", linewidth=1, alpha=0.7)
    ax_bot.axhline(y=_SELL_LINE, color="#F44336", linestyle="--", linewidth=1, alpha=0.7)
    buy_d = [day for day, value in zip(sent_dates, spread) if value <= _BUY_LINE]
    buy_v = [value for value in spread if value <= _BUY_LINE]
    sell_d = [day for day, value in zip(sent_dates, spread) if value >= _SELL_LINE]
    sell_v = [value for value in spread if value >= _SELL_LINE]
    if buy_d:
        ax_bot.scatter(buy_d, buy_v, color="#4CAF50", s=40, zorder=5, marker="^", label="买点 (≤-22.5%)")
    if sell_d:
        ax_bot.scatter(sell_d, sell_v, color="#F44336", s=40, zorder=5, marker="v", label="卖点 (≥52.5%)")
    for day in buy_d:
        ax_top.axvline(day, color="#4CAF50", linestyle="--", linewidth=0.9, alpha=0.7, zorder=1)
        ax_bot.axvline(day, color="#4CAF50", linestyle="--", linewidth=0.9, alpha=0.7, zorder=1)
    for day in sell_d:
        ax_top.axvline(day, color="#F44336", linestyle="--", linewidth=0.9, alpha=0.7, zorder=1)
        ax_bot.axvline(day, color="#F44336", linestyle="--", linewidth=0.9, alpha=0.7, zorder=1)
    span_start = min([sent_dates[0], *idx_dates])
    span_end = max([sent_dates[-1], *idx_dates])
    ax_top.set_xlim(span_start, span_end)
    ax_top.tick_params(axis="x", labelbottom=True)
    ax_bot.set_ylabel("多空差 (%)", fontsize=11, color="#e67e22", fontweight="bold")
    ax_bot.yaxis.set_tick_params(labelsize=9)
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_bot.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax_bot.xaxis.set_minor_locator(mdates.MonthLocator())
    ax_bot.tick_params(axis="x", labelsize=8, rotation=30)
    ax_bot.legend(loc="upper left", fontsize=9, framealpha=0.8)
    ax_bot_r = ax_bot.twinx()
    ax_bot_r.set_ylim(ax_bot.get_ylim())
    ax_bot_r.yaxis.set_tick_params(labelsize=9)
    ax_bot_r.set_ylabel("")

    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=150, bbox_inches="tight")
    plt.close(fig)
