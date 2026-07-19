import sys
from enum import Enum
from pathlib import Path

import typer
from script.config import Settings
from script.finalize import run_finalize
from script.pipeline import run_pipeline
from script.validate_source import validate_source

# CLI output is Traditional Chinese + the occasional ✅/❌ emoji. On a legacy
# Windows console (cp950) the emoji raises UnicodeEncodeError and crashes the
# command mid-print. Force UTF-8 on stdout/stderr so output never crashes on the
# console codepage (best-effort — a no-op where reconfigure is unavailable).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


class LlmChoice(str, Enum):
    company = "company"
    claude = "claude"


app = typer.Typer(help="Convert a prepared meeting transcript to structured minutes.")


@app.command()
def process(
    src: str = typer.Argument(..., help="Path to the prepared transcript file (UTF-8, MM:SS blocks)."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    model: str | None = typer.Option(
        None, "--model",
        help="Override OPENAI_MODEL for this run only (e.g. claude-opus-4-7, "
             "gpt-latest). Defaults to the .env value (medium, on-prem). Use a "
             "cloud model for non-confidential meetings where quality > privacy.",
    ),
    llm: LlmChoice | None = typer.Option(
        None, "--llm",
        help="Which LLM will process this meeting: 'company' (on-prem, "
             "confidential-safe) or 'claude' (the Claude session writes the "
             "JSON itself — use the /meetingminutes engine-B flow, not this full run). "
             "Required for a full run; not needed with --rerender.",
    ),
    force: bool = typer.Option(False, "--force", help="Ignore stage cache, re-run all stages."),
    rerender: bool = typer.Option(
        False, "--rerender",
        help="Skip LLM stages; re-render minutes.html + review_report.md "
             "from cached intermediate/minutes.json + review.json.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    if not rerender:
        if llm is None:
            typer.echo(
                "拒絕執行：整檔轉換必須明確指定 --llm。\n"
                "  --llm company  用公司地端 LLM（機密安全，逐字稿不出公司）\n"
                "  --llm claude   改走 /meetingminutes 的 engine-B 流程（由 Claude 本人寫 JSON 後 --rerender）",
            )
            raise typer.Exit(code=2)
        if llm is LlmChoice.claude:
            typer.echo(
                "--llm claude 不經由本 full-run 路徑。請用 /meetingminutes skill 的 "
                "engine-B 流程：讓 Claude 讀逐字稿、寫出 intermediate JSON，"
                "再執行 `process <src> --rerender`。",
            )
            raise typer.Exit(code=2)
    settings = Settings()
    if verbose:
        settings.log_level = "DEBUG"
    if model:
        settings.openai_model = model
    run_pipeline(
        src,
        settings=settings,
        name=name,
        force=force,
        rerender_only=rerender,
    )


@app.command()
def validate(
    src: str = typer.Argument(..., help="Path to the transcript file to check."),
) -> None:
    """Check a transcript is ready to process — LLM-free, metadata only.

    Prints readiness metadata (never transcript content) and exits non-zero
    when the source is not ready. Safe to run in either LLM mode: the output
    exposes no confidential text.
    """
    r = validate_source(src)
    typer.echo(f"檔案：{r.path}")
    typer.echo(f"存在：{r.exists}  UTF-8：{r.utf8}  非空：{r.non_empty}")
    typer.echo(f"時間戳行數：{r.timestamp_lines}  範圍：{r.first_timestamp}–{r.last_timestamp}")
    audio_info = f"（{r.audio_ext}）" if r.audio_ext else ""
    typer.echo(f"同名音檔：{'有' if r.has_sibling_audio else '無'}{audio_info}")
    if r.ok:
        typer.echo("結果：OK ✅")
    else:
        typer.echo("結果：NOT OK ❌")
        for p in r.problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=1)


@app.command()
def edit(
    src: str = typer.Argument(..., help="Output folder name (or transcript path) under out/."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    port: int = typer.Option(0, "--port", help="Port to bind (0 = auto-pick a free port)."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not auto-open the browser."),
) -> None:
    """Open the editable minutes page in a local browser to edit + export to Outlook."""
    from script.edit_server import serve
    settings = Settings()
    base = name or Path(src).stem
    out_dir = Path(settings.out_dir) / base
    if not (out_dir / "intermediate" / "synthesized.json").exists():
        typer.echo(
            f"找不到 {out_dir}/intermediate/synthesized.json — 請先對此會議跑 "
            f"`process ... --llm company`（或 --rerender）產生綜整結果。")
        raise typer.Exit(code=1)
    serve(out_dir, open_browser=not no_browser, port=port)


@app.command()
def finalize(
    src: str = typer.Argument(..., help="Transcript path or existing output folder name (used to locate out/<name>)."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    reuse: bool = typer.Option(
        False, "--reuse",
        help="Reuse the previous finalized.json as Q&A defaults (skip re-asking)."),
) -> None:
    """Interactively confirm the minutes and open an editable Outlook draft (not sent)."""
    settings = Settings()
    base_name = name or Path(src).stem
    out_dir = str(Path(settings.out_dir) / base_name)
    run_finalize(out_dir, default_subject=Path(src).stem, reuse=reuse)


if __name__ == "__main__":
    app()
