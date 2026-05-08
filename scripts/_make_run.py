"""Helper invoked by make.cmd ':run' to parse args + dispatch script.main.

Why a Python helper instead of pure batch?
  Windows CMD's %*-style argv parsing breaks too easily on quoted paths
  containing spaces and non-ASCII (CJK) chars combined with KEY=VALUE
  syntax. Python's sys.argv handles this correctly because CMD
  pre-tokenises before invoking the Python interpreter.

Accepts both forms uniformly:
  - Positional:   _make_run.py run "src/x.mp4" [name] [diarize]
  - KEY=VALUE :   _make_run.py run FILE="src/x.mp4" NAME=q2 DIARIZE=1
  - Mixed     :   ok too — KEY= prefixes always win over position
"""
import os
import subprocess
import sys
from pathlib import Path


def _split_kv(arg: str):
    """If arg starts with FILE=/NAME=/DIARIZE= return (key, value) else None."""
    for prefix in ("FILE=", "NAME=", "DIARIZE="):
        if arg.upper().startswith(prefix):
            return prefix[:-1], arg[len(prefix):]
    return None


def main(argv: list[str]) -> int:
    # argv[0] is always "run" (from make.cmd dispatch); skip it.
    args = argv[1:] if argv and argv[0].lower() == "run" else argv

    file_val = ""
    name_val = ""
    diarize_val = ""
    positional: list[str] = []

    for a in args:
        kv = _split_kv(a)
        if kv is None:
            positional.append(a)
        else:
            k, v = kv
            if k == "FILE":
                file_val = v
            elif k == "NAME":
                name_val = v
            elif k == "DIARIZE":
                diarize_val = v

    # Fill from positional only if KEY=VALUE didn't set
    if not file_val and len(positional) >= 1:
        file_val = positional[0]
    if not name_val and len(positional) >= 2:
        name_val = positional[1]
    if not diarize_val and len(positional) >= 3:
        diarize_val = positional[2]

    if not file_val:
        print("ERROR: FILE is required.", file=sys.stderr)
        print("Usage:", file=sys.stderr)
        print('  make run "path\\to\\meeting.mp4" [NAME] [DIARIZE: 0 or 1]', file=sys.stderr)
        print('  make run FILE="path\\to\\meeting.mp4" [NAME=name] [DIARIZE=1]', file=sys.stderr)
        return 1

    py = str(Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin") / "python")
    cmd = [py, "-m", "script.main", file_val]
    if name_val:
        cmd += ["--name", name_val]
    if diarize_val == "1":
        cmd += ["--diarize"]
    elif diarize_val == "0":
        cmd += ["--no-diarize"]

    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
