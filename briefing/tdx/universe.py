"""沪深 A-share quote list and the day bars used by breadth.

The prefix table lives here once. Denominators and the scanned universe
both use it. A missing day file is a read failure, not an exception.
"""

from __future__ import annotations

from pathlib import Path

from briefing.tdx.day import MISSING, read_day_bars

QUOTE_LIST = Path("T0002") / "hq_cache" / "specgpext.txt"
A_SHARE_PREFIXES = (
    "600",
    "601",
    "603",
    "605",
    "688",
    "689",
    "000",
    "001",
    "002",
    "003",
    "300",
    "301",
    "302",
)
CHINEXT_PREFIXES = ("300", "301", "302")


def quote_codes(tdx_dir: str | Path) -> list[str] | None:
    """Market 0 and market 1 A-share codes from the Tongdaxin quote list.

    Market 2 is Beijing and stays out, including codes that start with 9.
    A missing list is ``None``.
    """
    path = Path(tdx_dir) / QUOTE_LIST
    if not path.is_file():
        return None
    codes: list[str] = []
    seen: set[str] = set()
    text = path.read_bytes().decode("gbk", "replace")
    for line in text.splitlines():
        if not line.strip():
            continue
        market, code, *_rest = line.split("|")
        if market not in {"0", "1"}:
            continue
        if len(code) != 6 or not code.isdigit() or not code.startswith(A_SHARE_PREFIXES):
            continue
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _day_path(tdx_dir: Path, code: str) -> Path:
    market = "sh" if code.startswith("6") else "sz"
    return tdx_dir / "vipdoc" / market / "lday" / f"{market}{code}.day"


def load_a_share_universe(
    tdx_dir: str | Path,
    on_date: str,
    last_n: int = 260,
) -> tuple[list[dict], int]:
    """Load quote-list names and the bars on or before ``on_date``.

    ``last_n`` defaults to 260 so the close 60 market sessions back and the
    10-day ratio both sit inside the loaded tail. One unreadable day file
    increments the failure count and is omitted. The quote list itself
    being missing is one failure and an empty universe.
    """
    root = Path(tdx_dir)
    codes = quote_codes(root)
    if not codes:
        return [], 1
    universe: list[dict] = []
    failures = 0
    for code in codes:
        bars = read_day_bars(_day_path(root, code))
        if bars == MISSING or not isinstance(bars, list):
            failures += 1
            continue
        kept = [bar for bar in bars if bar["date"] <= on_date]
        if last_n is not None:
            kept = kept[-int(last_n) :]
        universe.append({"code": code, "name": code, "bars": kept})
    return universe, failures
