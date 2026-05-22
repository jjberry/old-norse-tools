"""Launch the Old Norse Tools web interface."""

import click
import uvicorn


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes")
def main(host: str, port: int, reload: bool) -> None:
    """Serve the Old Norse analysis web interface."""
    uvicorn.run(
        "nion.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
