"""`cosinabox add-stakeholder` — append a new stakeholder to stakeholders.yaml."""

from __future__ import annotations

import datetime
from pathlib import Path

import click
import yaml
from jsonschema import ValidationError, validate

from cosinabox.schemas import load_schema

CADENCE_CHOICES = click.Choice(["daily", "weekly", "biweekly", "monthly", "quarterly"])


@click.command("add-stakeholder")
@click.option("--name", required=True, help="Full name of the stakeholder.")
@click.option("--role", default="", help="Role or relationship description.")
@click.option("--cadence", required=True, type=CADENCE_CHOICES, help="Contact cadence.")
@click.option(
    "--last-contact",
    default=lambda: datetime.date.today().isoformat(),
    help="Last contact date (YYYY-MM-DD). Defaults to today.",
)
@click.option("--notes", default="", help="Optional notes about this stakeholder.")
@click.pass_context
def add_stakeholder_cmd(
    ctx: click.Context,
    name: str,
    role: str,
    cadence: str,
    last_contact: str,
    notes: str,
) -> None:
    """Add a new stakeholder to stakeholders.yaml."""
    config_dir: Path = ctx.obj["config_dir"]
    path = config_dir / "stakeholders.yaml"

    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    else:
        data = {"schema_version": 1, "stakeholders": []}

    stakeholders = data.get("stakeholders") or []

    # Reject duplicates
    existing_names = [s.get("name", "") for s in stakeholders]
    if name in existing_names:
        raise click.ClickException(f"Stakeholder '{name}' already exists.")

    # Build the new entry
    entry: dict = {"name": name, "cadence": cadence}
    if role:
        entry["role"] = role
    if last_contact:
        entry["last_contact"] = last_contact
    if notes:
        entry["notes"] = notes

    stakeholders.append(entry)
    data["stakeholders"] = stakeholders

    # Validate against schema
    schema = load_schema("stakeholders")
    try:
        validate(instance=data, schema=schema)
    except ValidationError as exc:
        raise click.ClickException(f"Schema validation failed: {exc.message}") from exc

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    click.echo(f"Added stakeholder: {name}")
