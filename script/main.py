from pathlib import Path

import typer
from script.config import Settings
from script.finalize import run_finalize
from script.pipeline import run_pipeline
from script.validate_source import validate_source


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
    force: bool = typer.Option(False, "--force", help="Ignore stage cache, re-run all stages."),
    rerender: bool = typer.Option(
        False, "--rerender",
        help="Skip LLM stages; re-render minutes.html + review_report.md "
             "from cached intermediate/minutes.json + review.json.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
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
    typer.echo(f"同名音檔：{r.has_sibling_audio} {r.audio_ext}")
    if r.ok:
        typer.echo("結果：OK ✅")
    else:
        typer.echo("結果：NOT OK ❌")
        for p in r.problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=1)


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
