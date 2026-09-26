"""In-memory snapshot, draft, and the commentary slot.

The commentary slot stays empty until D5. ``write_briefing`` refuses to
create the day's markdown while it is empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MISSING = "missing"


@dataclass
class Commentary:
    """D5 result: ``{text, metrics_used}``, or the missing mark."""

    text: str
    metrics_used: list[str] = field(default_factory=list)

    def is_missing(self) -> bool:
        return self.text.strip().lower() == MISSING


def missing_commentary() -> Commentary:
    """The slot D5 uses after a failed rewrite. ``metrics_used`` stays empty."""
    return Commentary(text=MISSING, metrics_used=[])


@dataclass
class Snapshot:
    """D3 signals, breadth, the three 50-day ratios, and the rank boards."""

    on_date: str
    signals: dict
    breadth: dict
    ma50: dict
    ranks: dict


@dataclass
class Draft:
    """One run's briefing, still in memory.

    ``commentary`` is ``None`` before D5. That empty slot is not the same
    as a commentary marked missing.
    """

    snapshot: Snapshot
    sentiment: dict | str
    commentary: Commentary | None = None
