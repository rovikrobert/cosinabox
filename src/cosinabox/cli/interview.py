"""`cosinabox interview` — drive the 10-step interview."""
from __future__ import annotations
from pathlib import Path
import click
from cosinabox.interview.state_machine import InterviewMachine

@click.command("interview")
@click.option("--start", is_flag=True, help="Begin a new interview.")
@click.option("--answer", default=None, help="Answer the current question.")
@click.option("--status", is_flag=True, help="Show progress.")
@click.pass_context
def interview_cmd(ctx: click.Context, start: bool, answer: str | None, status: bool) -> None:
    config_dir: Path = ctx.obj["config_dir"]
    if start:
        m = InterviewMachine(config_dir=config_dir)
        m.start()
        click.echo(m.next_question())
        return
    m = InterviewMachine.resume(config_dir=config_dir)
    if status:
        click.echo(f"Step {m.current_step_index + 1}/10 {'(complete)' if m.is_complete() else ''}")
        return
    if answer is not None:
        m.answer(answer)
        click.echo(m.next_question())
        return
    click.echo(m.next_question())
