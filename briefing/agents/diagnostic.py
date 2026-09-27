"""Choose extra evidence only when the diagnose checklist is not enough.

The agent reads files and git state. It does not edit code, the briefing,
or the specification. The skill still assigns the taxonomy category.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from briefing.skills.diagnose import checklist_view, diagnose_failure

_ROOT = Path(__file__).resolve().parents[2]
_BRIEFING = _ROOT / "briefing"


def diagnose(failure: dict, *, tools: dict | None = None) -> dict:
    """Return the skill's diagnosis, plus the files and functions involved."""
    evidence: list[str] = []
    if _needs_tools(failure):
        chosen = tools if tools is not None else _default_tools()
        evidence = _collect(failure, chosen)
    result = diagnose_failure(failure, evidence)
    files = [result["affected_module"]]
    for note in evidence:
        if note.startswith("已查看 briefing/") and note.removeprefix("已查看 ") not in files:
            files.append(note.removeprefix("已查看 ").strip())
    result["affected_files"] = files
    result["affected_functions"] = [result["affected_function"]] if result.get("affected_function") else []
    return result


def _needs_tools(failure: dict) -> bool:
    if failure.get("status") == "STOP" or "evaluator_error" in (failure.get("details") or {}):
        return False
    numbers = [number for number in (failure.get("requirement_failures") or []) if isinstance(number, int)]
    if numbers == [8] and not failure.get("sanity_failures"):
        return False
    if int(failure.get("prior_fixes") or 0) >= 3:
        return False
    view = checklist_view(failure)
    if not view["known"]:
        return True
    return len(view["categories"]) > 1


def _collect(failure: dict, tools: dict) -> list[str]:
    tools["git_status"]()
    tools["git_diff"]()
    notes = ["已查看 git status 与 git diff"]
    for path in _modules(failure):
        tools["read_file"](path)
        notes.append(f"已查看 {path}")
    tools["search_code"](_query(failure))
    notes.append("已按失败编号搜索代码")
    return notes


def _modules(failure: dict) -> list[str]:
    paths = list(checklist_view(failure)["modules"])
    if not paths:
        paths.append("briefing/evaluation/evaluator.py")
    return paths


def _query(failure: dict) -> str:
    numbers = [str(number) for number in (failure.get("requirement_failures") or [])]
    sanity = [name for name in (failure.get("sanity_failures") or []) if isinstance(name, str)]
    return " ".join([*numbers, *sanity]) or "failure"


def _default_tools() -> dict:
    return {
        "read_file": _read_file,
        "search_code": _search_code,
        "git_diff": _git_diff,
        "git_status": _git_status,
    }


def _read_file(path: str) -> str:
    target = Path(path)
    if not target.is_file():
        target = _ROOT / path
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def _search_code(query: str) -> list[str]:
    if not query.strip():
        return []
    hits: list[str] = []
    for path in _BRIEFING.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if query in text:
            hits.append(str(path.relative_to(_ROOT)).replace("\\", "/"))
        if len(hits) >= 20:
            break
    return hits


def _git_diff() -> str:
    return _git("diff", "--name-only")


def _git_status() -> str:
    return _git("status", "--porcelain")


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout
