import typer
from script.config import Settings
from script.pipeline import run_pipeline


app = typer.Typer(help="Convert meeting audio/video to structured Excel minutes.")


@app.command()
def process(
    src: str = typer.Argument(..., help="Path to audio/video file. (Ignored when --rerender; only used for review_report header.)"),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    force: bool = typer.Option(False, "--force", help="Ignore stage cache, re-run all stages."),
    skip_transcribe: bool = typer.Option(False, "--skip-transcribe", help="Reuse existing transcript.md only."),
    diarize: bool | None = typer.Option(
        None, "--diarize/--no-diarize",
        help="Override .env ENABLE_DIARIZATION for this run.",
    ),
    rerender: bool = typer.Option(
        False, "--rerender",
        help="Skip all expensive stages; re-render minutes.xlsx + review_report.md "
             "from cached intermediate/minutes.json + speaker_map.json.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    settings = Settings()
    if verbose:
        settings.log_level = "DEBUG"
    run_pipeline(
        src,
        settings=settings,
        name=name,
        force=force,
        skip_transcribe=skip_transcribe,
        diarize_override=diarize,
        rerender_only=rerender,
    )


if __name__ == "__main__":
    app()
