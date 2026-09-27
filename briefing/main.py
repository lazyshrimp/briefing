"""Write one day's briefing from the command line.

Commentary uses Cursor's Grok model when ``CURSOR_API_KEY`` is set.
``run_daily`` without a ``complete`` callable still leaves the commentary missing.
"""

from __future__ import annotations

import sys

from briefing.report.cursor_commentary import complete_with_cursor
from briefing.workflow.daily import run_daily


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m briefing.main YYYY-MM-DD", file=sys.stderr)
        return 2
    print(f"开始生成 {args[0]}。全程大约几分钟，每一步都会在这里显示。", flush=True)
    result = run_daily(
        args[0],
        complete=complete_with_cursor,
        progress=lambda message: print(message, flush=True),
    )
    print(result["status"], result.get("path") or "", flush=True)
    return 0 if result["status"] in {"PASS", "SKIP"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
