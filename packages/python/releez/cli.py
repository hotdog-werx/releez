import typer

app = typer.Typer(help='CLI tool for helping to manage release processes.')


def main() -> None:
    """Main entry point for the CLI."""
    app()
