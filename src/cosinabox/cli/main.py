"""cosinabox CLI entry point."""

from __future__ import annotations

import click


@click.group()
@click.version_option()
def cli() -> None:
    """CoSinaBox — open-source Chief of Staff."""


if __name__ == "__main__":
    cli()
