"""Load industry and concept block codes.

Industry names come from the Tongdaxin industry chain in ``incon.dat``
(fields whose code starts with ``T``). Only a code with no longer child is
kept: that is the ordinary sub-industry, such as 煤炭开采, not the parent
煤炭. A name is kept only when ``tdxzs.cfg`` has the same name. Style,
region, and broad-market names are not on that chain, so they stay out.

Concepts come only from ``#GN_`` headers in ``infoharbor_block.dat``.
"""

from __future__ import annotations

from pathlib import Path

STOP = "stop"


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    return raw.decode("gbk", errors="replace")


def load_block_maps(
    tdxzs_path: str | Path,
    incon_path: str | Path,
    infoharbor_path: str | Path,
) -> dict | str:
    """Return ``{industry, concept}`` lists of ``{code, name}``, or ``stop``."""
    tdxzs = Path(tdxzs_path)
    incon = Path(incon_path)
    infoharbor = Path(infoharbor_path)
    if not tdxzs.is_file() or not incon.is_file() or not infoharbor.is_file():
        return STOP

    chain: list[tuple[str, str]] = []
    for line in _read_text(incon).splitlines():
        parts = line.strip().split("|")
        if len(parts) >= 2 and parts[0].startswith("T") and parts[0][1:].isdigit() and parts[1]:
            chain.append((parts[0], parts[1]))
    codes = {code for code, _name in chain}
    industry_names = {
        name
        for code, name in chain
        if not any(other.startswith(code) and len(other) > len(code) for other in codes)
    }

    industry: list[dict] = []
    seen_codes: set[str] = set()
    for line in _read_text(tdxzs).splitlines():
        parts = line.strip().split("|")
        if len(parts) < 2:
            continue
        name, code = parts[0], parts[1]
        if name in industry_names and code not in seen_codes:
            seen_codes.add(code)
            industry.append({"code": code, "name": name})

    concept: list[dict] = []
    seen_concept: set[str] = set()
    for line in _read_text(infoharbor).splitlines():
        text = line.strip()
        if not text.startswith("#GN_"):
            continue
        parts = text[4:].split(",")
        if len(parts) < 3:
            continue
        name, code = parts[0], parts[2]
        if code.startswith("88") and code not in seen_concept:
            seen_concept.add(code)
            concept.append({"code": code, "name": name})

    return {"industry": industry, "concept": concept}
