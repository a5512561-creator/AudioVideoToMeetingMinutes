"""Guard against re-introducing a non-existent `process` subcommand.

`script/main.py` is a single-command Typer app, so the correct invocation is
`python -m script.main <transcript> [opts]`. Writing `python -m script.main
process <transcript>` makes Typer treat the literal string "process" as the
SRC argument and the real path becomes an unexpected extra argument. Shipped
tooling/docs must not contain that form.
"""
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_FILES = ["Makefile", "make.cmd", "scripts/_make_run.py", "README.md"]


def _normalize(text: str) -> str:
    # Collapse quotes/commas/whitespace so both the shell form
    # (`script.main process`) and the argv-list form
    # (`"script.main", "process"`) reduce to `script.mainprocess`.
    return re.sub(r"""["',\s]""", "", text)


def test_no_process_subcommand_in_tooling_or_docs():
    offenders = []
    for rel in _FILES:
        for lineno, line in enumerate(
            (_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1
        ):
            if "script.mainprocess" in _normalize(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "`script.main` is a single-command Typer app — there is no `process` "
        "subcommand. Remove it from:\n" + "\n".join(offenders)
    )
