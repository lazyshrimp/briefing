"""Read one code's value on one date from Tongdaxin extdata.

``.idx`` records are 29 bytes: market ``uint16``, 6-byte ASCII code, padding,
then a ``uint32`` count at offset 25.

``.dat`` records are 12 bytes: date ``uint32`` (YYYYMMDD), a reserved float,
then the rank or count as a float at offset 8.
"""

from __future__ import annotations

import struct
from pathlib import Path

from briefing.tdx.day import to_date_str

IDX_SIZE = 29
DAT_SIZE = 12
MISSING = "missing"


def _date_int(value: str | int) -> int:
    return int(to_date_str(value).replace("-", ""))


def read_extdata_series(
    extdata_dir: str | Path,
    ext_num: int,
    code: str,
    on_date: str | int,
) -> float | str:
    """Return the numeric value for ``code`` on ``on_date``, or ``missing``.

    A missing file, an unknown code, or a date that is not in that code's
    series is ``missing``. A real zero stays ``0.0`` and is not replaced
    with an empty string.
    """
    directory = Path(extdata_dir)
    idx_path = directory / f"extdata_{ext_num}.idx"
    dat_path = directory / f"extdata_{ext_num}.dat"
    if not idx_path.is_file() or not dat_path.is_file():
        return MISSING

    code_bytes = str(code).strip().encode("ascii")
    target = _date_int(on_date)
    idx_data = idx_path.read_bytes()
    records = len(idx_data) // IDX_SIZE
    data_offset = 0

    for index in range(records):
        base = index * IDX_SIZE
        rec_code = idx_data[base + 2 : base + 8].rstrip(b"\x00")
        count = struct.unpack_from("<I", idx_data, base + 25)[0]
        if rec_code == code_bytes:
            if count == 0:
                return MISSING
            with dat_path.open("rb") as handle:
                handle.seek(data_offset)
                raw = handle.read(count * DAT_SIZE)
            if len(raw) < count * DAT_SIZE:
                return MISSING
            for point in range(count):
                off = point * DAT_SIZE
                date_val = struct.unpack_from("<I", raw, off)[0]
                if date_val == target:
                    return float(struct.unpack_from("<f", raw, off + 8)[0])
            return MISSING
        data_offset += count * DAT_SIZE
    return MISSING


def read_new_high_net(extdata_dir: str | Path, on_date: str | int) -> int | float | str:
    """Return 新高家数 − 新低家数 from ``extdata_13``, or ``missing``.

    The file has one market series. Separate high and low counts are not stored.
    A whole number is returned as an int.
    """
    value = read_market_extdata(extdata_dir, 13, on_date)
    if value == MISSING:
        return MISSING
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def read_market_extdata(
    extdata_dir: str | Path,
    ext_num: int,
    on_date: str | int,
) -> float | str:
    """Read the first index entry of a market-wide file such as extdata_4/5/6/13.

    These files hold one market series. When Tongdaxin writes several index
    entries, their series are identical, so the first entry is the market value.
    """
    directory = Path(extdata_dir)
    idx_path = directory / f"extdata_{ext_num}.idx"
    if not idx_path.is_file():
        return MISSING
    idx_data = idx_path.read_bytes()
    if len(idx_data) < IDX_SIZE:
        return MISSING
    code = idx_data[2:8].rstrip(b"\x00").decode("ascii", errors="replace")
    if not code:
        return MISSING
    return read_extdata_series(directory, ext_num, code, on_date)
