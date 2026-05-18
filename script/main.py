import typer
from script.config import Settings
from script.pipeline import run_pipeline


app = typer.Typer(help="Convert a prepared meeting transcript to structured minutes.")


@app.command()
def process(
    src: str = typer.Argument(..., help="Path to the prepared transcript file (UTF-8, MM:SS blocks)."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
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
    run_pipeline(
        src,
        settings=settings,
        name=name,
        force=force,
        rerender_only=rerender,
    )


if __name__ == "__main__":
    app()
