"""50-day ratios: numerators are used as given, denominators follow the quote list."""

from __future__ import annotations

from pathlib import Path

import pytest

from briefing.analysis.ma50 import HS300_CONSTITUENTS, a_share_denominators, ma50_ratios

TDX = Path(r"C:\zd_pazq_hy")
QUOTE = TDX / "T0002" / "hq_cache" / "specgpext.txt"
live = pytest.mark.skipif(not QUOTE.is_file(), reason="skip")


def test_ratio_is_exact_and_does_not_drop_the_numerator() -> None:
    ratios = ma50_ratios(
        hs300_above=150,
        hs300_total=HS300_CONSTITUENTS,
        chinext_above=10,
        chinext_total=20,
        all_a_above="missing",
        all_a_total=100,
    )
    assert ratios["hs300"] == {"above": 150.0, "total": 300, "pct": 150 / 300}
    assert ratios["chinext"]["pct"] == 0.5
    assert ratios["all_a"] == "missing"


def test_zero_denominator_is_missing() -> None:
    ratios = ma50_ratios(
        hs300_above=1,
        hs300_total=0,
        chinext_above=1,
        chinext_total="missing",
        all_a_above=1,
        all_a_total=1,
    )
    assert ratios["hs300"] == "missing"
    assert ratios["chinext"] == "missing"
    assert ratios["all_a"]["pct"] == 1


def test_denominators_use_the_quote_list_and_skip_beijing(tmp_path: Path) -> None:
    quote = tmp_path / "T0002" / "hq_cache" / "specgpext.txt"
    quote.parent.mkdir(parents=True)
    quote.write_bytes(
        "\n".join(
            [
                "0|000001|平安",
                "0|300001|创业",
                "0|301001|创业二",
                "0|302132|创业三",
                "0|399006|指数",
                "1|600000|浦发",
                "1|689009|九号",
                "2|920000|北交",
            ]
        ).encode("gbk")
    )

    counted = a_share_denominators(tmp_path)
    assert counted["hs300"] == 300
    assert counted["chinext"] == 3
    assert counted["all_a"] == 6


def test_denominators_missing_when_the_quote_list_is_absent(tmp_path: Path) -> None:
    assert a_share_denominators(tmp_path) == "missing"


@live
def test_live_denominators_match_the_quote_list_without_beijing() -> None:
    counted = a_share_denominators(TDX)
    assert isinstance(counted, dict)
    text = QUOTE.read_bytes().decode("gbk", "replace")
    codes = []
    for line in text.splitlines():
        market, code, *_rest = line.split("|")
        if market in {"0", "1"} and code[:3] in {
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
        }:
            codes.append(code)
    assert counted["all_a"] == len(codes)
    assert counted["chinext"] == sum(code.startswith(("300", "301", "302")) for code in codes)
    assert counted["hs300"] == 300
    assert all(not code.startswith("9") for code in codes)
