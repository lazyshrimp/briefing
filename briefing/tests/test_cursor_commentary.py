"""Cursor commentary parses model JSON and does not store the API key."""

from __future__ import annotations

from pathlib import Path

import pytest

from briefing.report.cursor_commentary import complete_with_cursor
from cursor_sdk import AgentOptions, LocalAgentOptions

ROOT = Path(__file__).resolve().parents[2]


def test_a_json_reply_becomes_the_commentary_payload() -> None:
    seen = {}

    def ask(prompt, api_key, model):
        seen["prompt"] = prompt
        seen["model"] = model
        return '{"text": "净值为 7。", "metrics_used": ["net"]}'

    payload = complete_with_cursor("可用指标：\n- net=7", ask=ask, api_key="test-key", model="grok-4.7")
    assert payload == {"text": "净值为 7。", "metrics_used": ["net"]}
    assert seen["model"] == "grok-4.7"
    assert "net=7" in seen["prompt"]
    assert api_key_absent(seen)


def test_fenced_json_is_accepted() -> None:
    def ask(prompt, api_key, model):
        return '```json\n{"text": "横盘 25%。", "metrics_used": ["flat"]}\n```'

    payload = complete_with_cursor("prompt", ask=ask, api_key="test-key")
    assert payload["metrics_used"] == ["flat"]
    assert payload["text"] == "横盘 25%。"


def test_a_missing_key_raises_before_any_model_call(monkeypatch) -> None:
    monkeypatch.setattr("briefing.report.cursor_commentary._load_env", lambda: None)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CURSOR_API_KEY"):
        complete_with_cursor("prompt")


def test_the_agent_is_text_only() -> None:
    options = AgentOptions(model="grok-4.7", api_key="test-key", tools=[], local=LocalAgentOptions(cwd="."))
    assert options.tools == []
    assert options.model == "grok-4.7"
    source = (ROOT / "briefing" / "report" / "cursor_commentary.py").read_text(encoding="utf-8")
    assert "crsr_" not in source
    assert "tools=[]" in source


def api_key_absent(seen: dict) -> bool:
    return "crsr_" not in str(seen)
