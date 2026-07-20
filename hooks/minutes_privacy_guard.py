"""PreToolUse hook: block the cloud session from reading protected files while
a company-mode lock is active.

Company mode writes `.minutes-company-lock.json` ({"protected": [paths]}) into
the meeting folder. This hook denies any Read / Grep / Glob / Bash tool call
that targets one of those paths, so the confidential transcript/audio can never
be ingested by the cloud LLM. Absent lock -> never blocks.

The Bash guard is best-effort only. It discovers the lock from cwd AND from the
directories of path-like tokens in the command (so it engages even when cwd is
the repo root and the lock lives in a meeting subfolder), then string-scans the
command for protected paths. It remains bypassable — a determined command can
still evade the scan (globbing, encoding, variable expansion, copying the file
first). The hard guarantee comes from the exact-path Read / Grep / Glob block,
plus the company-mode skill asking the user first. Do not rely on the Bash scan
as a security boundary.
"""
import json
import os
import re
import sys
from pathlib import Path

_READ_TOOLS = ("Read", "Grep", "Glob")

# Tokens in a shell command that look like file paths — used to discover a
# lock that lives beside a referenced file (Bash cwd alone is not enough).
_CMD_TOKEN_RE = re.compile(r"""[^\s"'|&;<>()]+""")
_PATHISH_EXT = (".vtt", ".txt", ".md", ".m4a", ".mp3", ".wav", ".ogg", ".aac",
                ".mp4", ".mov", ".mkv")  # video recordings count as protected media


def _command_path_dirs(cmd: str) -> list[str]:
    """Parent directories of path-like tokens in a shell command (best-effort)."""
    dirs = []
    for tok in _CMD_TOKEN_RE.findall(cmd or ""):
        if "/" in tok or "\\" in tok or tok.lower().endswith(_PATHISH_EXT):
            try:
                dirs.append(str(Path(tok).parent))
            except (OSError, ValueError):
                pass
    return dirs


def _norm(p: str) -> str:
    """Normalise a path for case-insensitive, separator-agnostic comparison (Windows-safe)."""
    try:
        return str(Path(p)).replace("\\", "/").casefold()
    except (TypeError, ValueError):
        return str(p or "").replace("\\", "/").casefold()


def _resolve(path: str, base_dir=None) -> str:
    """Canonical, comparable form of a path.

    Anchors a relative path against base_dir, then collapses `..` and resolves
    symlinks so two spellings of the same file compare equal (closes the
    `a/../b` bypass). Falls back to lexical normpath for paths that can't be
    resolved (e.g. don't exist on this machine)."""
    p = Path(path or "")
    if not p.is_absolute() and base_dir is not None:
        p = Path(base_dir) / p
    try:
        p = p.resolve()
    except (OSError, RuntimeError, ValueError):
        p = Path(os.path.normpath(str(p)))
    return str(p).replace("\\", "/").casefold()


def find_lock(start_dir):
    """Walk up from start_dir looking for .minutes-company-lock.json.

    Returns (lock_dict, lock_dir) or (None, None). A corrupt/unreadable lock
    fails CLOSED: returns ({"protected": ["*"]}, that_dir).
    """
    if not start_dir:
        return None, None
    try:
        d = Path(start_dir).resolve()
    except (OSError, ValueError):
        return None, None
    for cand in (d, *d.parents):
        lp = cand / ".minutes-company-lock.json"
        if lp.exists():
            try:
                return json.loads(lp.read_text(encoding="utf-8")), cand
            except (json.JSONDecodeError, OSError):
                return {"protected": ["*"]}, cand
    return None, None


def should_block(tool_name: str, tool_input: dict, lock: dict | None, lock_dir: str | None = None) -> tuple[bool, str]:
    """Return (blocked, reason). `lock` is the parsed lock dict or None.

    Protected paths are resolved against `lock_dir` when relative, so a lock
    written with meeting-relative filenames still matches absolute tool targets.
    A wildcard lock (`{"protected": ["*"]}`, the fail-closed corrupt case)
    blocks every read-ish tool.
    """
    protected = list((lock or {}).get("protected", []))
    if not protected:
        return False, ""
    reason = ("隱私鎖：本次會議選擇公司地端 LLM，逐字稿／錄音檔不得被雲端 LLM 讀取。"
              "此檔案在保護清單中，已封鎖。")
    reason_corrupt = "隱私鎖檔毀損，為安全起見封鎖所有讀取。請檢查 .minutes-company-lock.json。"

    # Fail-closed wildcard: corrupt lock blocks all read-ish tools.
    if protected == ["*"]:
        if tool_name in _READ_TOOLS + ("Bash",):
            return True, reason_corrupt
        return False, ""

    protected_norm = {_resolve(p, lock_dir) for p in protected}

    if tool_name in _READ_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        if _resolve(target) in protected_norm:
            return True, reason
        return False, ""

    if tool_name == "Bash":
        # Best-effort only: a shell command has no single target path and no
        # meaningful base_dir, so we do a lexical scan with _norm (no symlink /
        # `..` canonicalisation like the Read/Grep/Glob path). Bypassable — the
        # hard guarantee is the exact-path block above, not this.
        cmd = _norm(tool_input.get("command", ""))
        # Best-effort string scan (see module docstring): match by normalised
        # full path or basename appearing anywhere in the command.
        for pn in protected_norm:
            if pn in cmd or Path(pn).name.casefold() in cmd:
                return True, reason
        return False, ""

    return False, ""


def main() -> int:
    """Harness entry: read the tool call from stdin, block if needed.

    PreToolUse contract: exit code 2 blocks the tool call and shows stderr to
    Claude; exit code 0 allows it. The lock is discovered by walking up from the
    target file's directory (read tools), or from cwd plus the directories of
    path-like tokens in the command (Bash), so protection works even when the
    session cwd is the repo root and the lock lives in the meeting subfolder.
    """
    for stream in (sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # py3.7+; harmless if unavailable
        except (AttributeError, ValueError):
            pass

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse -> don't interfere

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name in _READ_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        start_dirs = [str(Path(target).parent)] if target else [str(Path.cwd())]
    elif tool_name == "Bash":
        start_dirs = [str(Path.cwd())] + _command_path_dirs(tool_input.get("command", ""))
    else:
        start_dirs = [str(Path.cwd())]

    for sd in start_dirs:
        lock, lock_dir = find_lock(sd)
        if not lock:
            continue
        blocked, reason = should_block(tool_name, tool_input, lock, lock_dir)
        if blocked:
            try:
                sys.stderr.write(reason)
            except Exception:
                pass  # a failed message must not turn a block (exit 2) into exit 1
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
