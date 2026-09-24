"""Read one Tongdaxin `.day` file.

A record is 32 bytes, little-endian, packed with ``struct`` format ``<IIIIIfII``:

- date, open, high, low, close: unsigned 32-bit integers
- amount: float 32
- volume, reserved: unsigned 32-bit integers

Prices are stored in fen. Divide by 100 to get yuan.
"""

from __future__ import annotations

import struct
from datetime import date, datetime
from pathlib import Path

RECORD = struct.Struct("<IIIIIfII")
RECORD_SIZE = RECORD.size
MISSING = "missing"


def to_date_str(value: date | datetime | str | int) -> str:
    """Normalize a date to ``YYYY-MM-DD``."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def read_day_bars(path: str | Path, last_n: int | None = None) -> list[dict] | str:
    """Return ascending ``{date, close, volume}`` bars, or ``missing``.

    ``close`` is already divided by 100. ``volume`` is the raw share count
    from the file. A zero volume marks a day with no trades. Signals read
    ``close`` only. Breadth uses ``volume == 0`` to drop that stock from
    the day's high, low, 4% and 25% counts. This is not a turnover floor.

    A missing file, or a length that is not a multiple of 32, is ``missing``.
    Dates must be strictly increasing.
    """
    day_path = Path(path)
    if not day_path.is_file():
        return MISSING
    size = day_path.stat().st_size
    if size == 0 or size % RECORD_SIZE != 0:
        return MISSING

    count = size // RECORD_SIZE
    start = 0
    if last_n is not None:
        count = min(int(last_n), count)
        start = (size // RECORD_SIZE) - count

    with day_path.open("rb") as handle:
        handle.seek(start * RECORD_SIZE)
        raw = handle.read(count * RECORD_SIZE)

    bars: list[dict] = []
    previous: str | None = None
    for index in range(count):
        date_int, _open, _high, _low, close, _amount, _volume, _reserved = RECORD.unpack_from(
            raw, index * RECORD_SIZE
        )
        iso = f"{date_int // 10000:04d}-{(date_int % 10000) // 100:02d}-{date_int % 100:02d}"
        if previous is not None and iso <= previous:
            return MISSING
        previous = iso
        bars.append({"date": iso, "close": close / 100.0, "volume": int(_volume)})
    return bars
