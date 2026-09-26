"""Write a candidate rank fixture for 2026-09-24. A person confirms it later."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from briefing.analysis.ranks import daily_top10, rps_top10
from briefing.tdx.blocks import load_block_maps

TDX = Path(r"C:\zd_pazq_hy")
ON_DATE = "2026-09-24"
OUT = Path(__file__).parent / "fixtures" / "golden_ranks_20260924.json"


def _row(item: dict) -> dict:
    pct = item["pct"]
    row = {
        "name": item["name"],
        "code": item["code"],
        "pct": pct if pct == "missing" else round(float(pct), 4),
    }
    if "rps" in item:
        row["rps"] = item["rps"]
    return row


def _already_confirmed() -> bool:
    if not OUT.is_file():
        return False
    return bool(json.loads(OUT.read_text(encoding="utf-8")).get("confirmed_by_human"))


def main() -> int:
    if _already_confirmed() and "--force" not in sys.argv:
        print(f"{OUT} is confirmed by a person; rerun with --force to replace it", file=sys.stderr)
        return 1
    groups = load_block_maps(
        TDX / "T0002" / "hq_cache" / "tdxzs.cfg",
        TDX / "incon.dat",
        TDX / "T0002" / "hq_cache" / "infoharbor_block.dat",
    )
    lday = TDX / "vipdoc" / "sh" / "lday"
    extdata = TDX / "T0002" / "extdata"
    daily = daily_top10(groups, lday, ON_DATE)
    rps = rps_top10(groups, lday, extdata, ON_DATE)
    payload = {
        "confirmed_by_human": False,
        "date": ON_DATE,
        "industry_daily": [_row(item) for item in daily["industry"]["items"]],
        "concept_daily": [_row(item) for item in daily["concept"]["items"]],
        "industry_rps_15": [_row(item) for item in rps["industry"][15]["items"]],
        "concept_rps_15": [_row(item) for item in rps["concept"][15]["items"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
