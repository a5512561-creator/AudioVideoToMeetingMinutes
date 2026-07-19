"""PreToolUse hook: block the cloud session from reading protected files while
a company-mode lock is active.

Company mode writes `.minutes-company-lock.json` ({"protected": [paths]}) into
the meeting folder. This hook denies any Read / Grep / Glob / Bash tool call
that targets one of those paths, so the confidential transcript/audio can never
be ingested by the cloud LLM. Absent lock -> never blocks.
"""
import json
import sys
from pathlib import Path

_READ_TOOLS = ("Read", "Grep", "Glob")


def _norm(p: str) -> str:
    """Normalise a path for comparison (resolve separators + case on Windows)."""
    try:
        return str(Path(p)).replace("\\", "/").casefold()
    except (TypeError, ValueError):
        return str(p or "").replace("\\", "/").casefold()


def should_block(tool_name: str, tool_input: dict, lock) -> tuple[bool, str]:
    """Return (blocked, reason). `lock` is the parsed lock dict or None."""
    protected = list((lock or {}).get("protected", []))
    if not protected:
        return False, ""
    protected_norm = {_norm(p) for p in protected}

    reason = (
        "隱私鎖：本次會議選擇公司地端 LLM，逐字稿／錄音檔不得被雲端 LLM 讀取。"
        "此檔案在保護清單中，已封鎖。"
    )

    if tool_name in _READ_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        if _norm(target) in protected_norm:
            return True, reason
        return False, ""

    if tool_name == "Bash":
        cmd = _norm(tool_input.get("command", ""))
        # Block if any protected path (by normalised full path or basename)
        # appears in the command string.
        for pn in protected_norm:
            if pn in cmd or Path(pn).name.casefold() in cmd:
                return True, reason
        return False, ""

    return False, ""


def _load_lock() -> dict | None:
    lock_path = Path.cwd() / ".minutes-company-lock.json"
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Fail CLOSED: a corrupt lock in a company-mode folder must not silently
        # disable protection. Treat as "everything protected in this folder".
        return {"protected": ["*"]}


def main() -> int:
    """Harness entry: read the tool call from stdin, block if needed.

    PreToolUse contract: exit code 2 blocks the tool call and shows stderr to
    Claude; exit code 0 allows it.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse -> don't interfere

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    lock = _load_lock()

    # Wildcard lock (corrupt file, fail-closed): block all read-ish tools.
    if lock == {"protected": ["*"]} and tool_name in _READ_TOOLS + ("Bash",):
        sys.stderr.write("隱私鎖檔毀損，為安全起見封鎖所有讀取。請檢查 .minutes-company-lock.json。")
        return 2

    blocked, reason = should_block(tool_name, tool_input, lock)
    if blocked:
        sys.stderr.write(reason)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
