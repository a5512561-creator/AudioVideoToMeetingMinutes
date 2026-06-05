"""Guard against reverting to the bare `script.main <path>` invocation form.

`script/main.py` is a multi-command Typer app with `process` and `finalize`
subcommands.  Every invocation must name a subcommand immediately after
`script.main`; the bare form `python -m script.main <src>` is broken (Typer
treats <src> as a command name and raises "No such command").

This test enforces two concrete invariants that would catch a regression:

1. `scripts/_make_run.py` — the built command list must contain the adjacent
   tokens ``"script.main", "process"`` (i.e. `"process"` immediately follows
   `"script.main"` in the argv list literal).

2. `Makefile` — every line that contains ``script.main`` and looks like a
   shell invocation (contains ``-m script.main``) must be immediately followed
   by a known subcommand token (`process` or `finalize`).

Both assertions would fail if someone reverted the fixes and reinstated the
bare `script.main <path>` form.
"""
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_KNOWN_SUBCOMMANDS = {"process", "finalize"}


def test_make_run_uses_process_subcommand():
    """scripts/_make_run.py must contain "script.main", "process" adjacently."""
    src = (_ROOT / "scripts/_make_run.py").read_text(encoding="utf-8")
    # Match the literal list construction: "script.main", "process"
    # Allow any quote style and optional whitespace.
    pattern = re.compile(
        r"""["']script\.main["']\s*,\s*["']process["']"""
    )
    assert pattern.search(src), (
        'scripts/_make_run.py must build the command list with '
        '"script.main", "process" adjacent. '
        'Bare `script.main <path>` is broken in multi-command mode.'
    )


def test_makefile_script_main_lines_have_subcommand():
    """Every `$(PY) -m script.main ...` line in Makefile must name a subcommand."""
    lines = (_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    offenders = []
    for lineno, line in enumerate(lines, 1):
        if "-m script.main" not in line:
            continue
        # Extract the token immediately after "script.main"
        m = re.search(r"-m\s+script\.main\s+(\S+)", line)
        if m is None:
            offenders.append(f"Makefile:{lineno}: could not parse token after script.main: {line.strip()}")
            continue
        next_token = m.group(1).strip("\"'$()")
        # Strip Make variable references like $(NAME)
        next_token = re.sub(r"\$\(.*?\)", "", next_token).strip("\"'")
        if next_token not in _KNOWN_SUBCOMMANDS:
            offenders.append(
                f"Makefile:{lineno}: expected subcommand ({', '.join(sorted(_KNOWN_SUBCOMMANDS))}) "
                f"after script.main, got {next_token!r}: {line.strip()}"
            )
    assert not offenders, (
        "script/main.py is multi-command — every `python -m script.main` "
        "invocation must name a subcommand. Fix:\n" + "\n".join(offenders)
    )
