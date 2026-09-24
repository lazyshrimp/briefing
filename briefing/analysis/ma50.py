"""Three ratios of stocks whose close is above their own 50-day average.

Numerators come from extdata_4 (沪深 A), extdata_5 (沪深300) and extdata_6
(创业板). They are not filtered again for ST or a zero-volume day.

Denominators stay at the sizes in requirement 3.2. 沪深300 is the constituent
count, 300, and does not shrink when a member is halted or newly listed.
沪深 A and 创业板 are counts from Tongdaxin's quote list
``T0002/hq_cache/specgpext.txt``: market 0 and market 1 only. Market 2 is
Beijing, including codes that start with 9, and stays out. A day file left
behind after delisting is not a listed name. 创业板 is the 300, 301 and 302
codes inside that same list. A short history does not shrink the count.
"""

from __future__ import annotations

from pathlib import Path

from briefing.tdx.universe import CHINEXT_PREFIXES, quote_codes

MISSING = "missing"
HS300_CONSTITUENTS = 300


def _ratio(above: float | str | None, total: int | str | None) -> dict | str:
    if above == MISSING or above is None or total == MISSING or total is None:
        return MISSING
    if isinstance(total, str) or total <= 0:
        return MISSING
    above_value = float(above)
    return {"above": above_value, "total": total, "pct": above_value / total}


def ma50_ratios(
    *,
    hs300_above: float | str | None,
    hs300_total: int | str | None,
    chinext_above: float | str | None,
    chinext_total: int | str | None,
    all_a_above: float | str | None,
    all_a_total: int | str | None,
) -> dict[str, dict | str]:
    """Return ``{hs300, chinext, all_a}``, each ``{above, total, pct}`` or ``missing``."""
    return {
        "hs300": _ratio(hs300_above, hs300_total),
        "chinext": _ratio(chinext_above, chinext_total),
        "all_a": _ratio(all_a_above, all_a_total),
    }


def a_share_denominators(tdx_dir: str | Path) -> dict[str, int] | str:
    """Count the Tongdaxin quote list. Does not drop a short history."""
    codes = quote_codes(tdx_dir)
    if not codes:
        return MISSING
    chinext_total = sum(code.startswith(CHINEXT_PREFIXES) for code in codes)
    return {
        "hs300": HS300_CONSTITUENTS,
        "chinext": chinext_total,
        "all_a": len(codes),
    }
