"""Ask Cursor's Grok model for the market commentary.

The key stays in the environment or a gitignored ``.env``. This function
does not write it down. The agent is text-only: no built-in tools, and its
working directory is an empty temporary folder, so it cannot edit the briefing.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

_DEFAULT_MODEL = "grok-4.7"
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def complete_with_cursor(prompt: str, *, ask=None, api_key: str | None = None, model: str | None = None) -> dict:
    """Return ``{text, metrics_used}`` from Grok, or raise when the call fails."""
    _load_env()
    key = api_key if api_key is not None else os.environ.get("CURSOR_API_KEY", "")
    chosen = (model or os.environ.get("CURSOR_COMMENTARY_MODEL") or _DEFAULT_MODEL).strip()
    if ask is None:
        if not str(key).strip():
            raise RuntimeError("CURSOR_API_KEY is not set")
        text = _ask_cursor(prompt, str(key).strip(), chosen)
    else:
        text = ask(prompt, key, chosen)
    return _payload(text)


def _ask_cursor(prompt: str, api_key: str, model: str) -> str:
    return asyncio.run(_ask(prompt, api_key, model))


async def _ask(prompt: str, api_key: str, model: str) -> str:
    from cursor_sdk import AgentOptions, AsyncAgent, AsyncClient, LocalAgentOptions

    if "上次未通过的原因" in prompt:
        print(f"评论未通过，正在用 {model} 重写一次。这一步大约一到两分钟。", flush=True)
    else:
        print(f"正在用 {model} 写评论。这一步大约一到两分钟。", flush=True)
    with tempfile.TemporaryDirectory(prefix="briefing-commentary-") as folder:
        async with await AsyncClient.launch_bridge(workspace=folder) as client:
            result = await AsyncAgent.prompt(
                prompt,
                AgentOptions(
                    model=model,
                    api_key=api_key,
                    tools=[],
                    local=LocalAgentOptions(cwd=folder),
                ),
                client=client,
            )
    status = str(getattr(result.status, "value", result.status)).lower()
    if "finished" not in status:
        raise RuntimeError(f"commentary run {status}")
    if not result.result or not str(result.result).strip():
        raise RuntimeError("commentary run returned empty text")
    return str(result.result)


def _payload(text: str) -> dict:
    parsed = _extract_json(text)
    if parsed is None:
        stripped = text.strip()
        if not stripped:
            raise RuntimeError("commentary text is empty")
        return {"text": stripped, "metrics_used": []}
    return parsed


def _extract_json(text: str) -> dict | None:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    for blob in (candidate, _object_slice(candidate)):
        if not blob:
            continue
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("text"), str)
            and payload["text"].strip()
            and isinstance(payload.get("metrics_used"), list)
            and all(isinstance(item, str) for item in payload["metrics_used"])
        ):
            return {"text": payload["text"].strip(), "metrics_used": list(payload["metrics_used"])}
    return None


def _object_slice(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ""
    return text[start : end + 1]


def _load_env() -> None:
    if not _ENV_FILE.is_file():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())
