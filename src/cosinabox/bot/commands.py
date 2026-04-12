"""Telegram bot commands: /help, /status, /cost, /brief.

Each command is a standalone async handler that receives the Telegram
Update + context. They are registered in App.run() alongside the DM
message handler.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from telegram import Update

logger = logging.getLogger(__name__)


async def cmd_help(update: Update, _ctx: Any) -> None:
    """Show available commands."""
    text = (
        "Commands:\n"
        "/help — This message\n"
        "/status — Enabled integrations, jobs, and stakeholder count\n"
        "/cost — Today's API spend vs. daily cap\n"
        "/brief — On-demand briefing (runs the morning briefing prompt)\n"
        "/analytics — Operational metrics (cost, tools, job health)"
    )
    if update.message:
        await update.message.reply_text(text)


def build_status_handler(
    *,
    name: str,
    timezone: str,
    tool_definitions: list[dict[str, Any]],
    jobs_config: dict[str, Any],
    stakeholder_count: int,
) -> Any:
    """Build a /status handler with baked-in config context."""

    async def cmd_status(update: Update, _ctx: Any) -> None:
        enabled_jobs = [k for k, v in jobs_config.items() if v.get("enabled")]
        tool_names = [d["name"] for d in tool_definitions]

        lines = [
            f"Name: {name}",
            f"Timezone: {timezone}",
            f"Tools: {len(tool_names)} ({', '.join(tool_names) or 'none'})",
            f"Jobs: {', '.join(enabled_jobs) or 'none'}",
            f"Stakeholders: {stakeholder_count}",
        ]
        if update.message:
            await update.message.reply_text("\n".join(lines))

    return cmd_status


def build_cost_handler(
    *,
    cost_tracker: Any,
) -> Any:
    """Build a /cost handler with access to the cost tracker."""

    async def cmd_cost(update: Update, _ctx: Any) -> None:
        today = datetime.now(UTC).date()
        today_spend = cost_tracker.spend_on(today)
        cap = cost_tracker.daily_cap_usd
        pct = (today_spend / cap * 100) if cap > 0 else 0

        lines = [
            f"Today: ${today_spend:.2f} / ${cap:.2f} ({pct:.0f}%)",
        ]

        # Show last 3 days if available
        for days_ago in range(1, 4):
            d = date.fromordinal(today.toordinal() - days_ago)
            spend = cost_tracker.spend_on(d)
            if spend > 0:
                lines.append(f"  {d.isoformat()}: ${spend:.2f}")

        if update.message:
            await update.message.reply_text("\n".join(lines))

    return cmd_cost


def build_brief_handler(
    *,
    agent_loop: Any,
    chat_id: str,
) -> Any:
    """Build a /brief handler that runs an on-demand briefing via the agent loop."""

    async def cmd_brief(update: Update, _ctx: Any) -> None:
        if update.message:
            await update.message.reply_text("Generating briefing...")

        prompt = (
            "Give me a quick briefing: my top priorities right now, "
            "any upcoming events today or tomorrow, and anything I "
            "should be thinking about. Keep it concise."
        )

        try:
            result = agent_loop.run(
                prompt=prompt,
                session_id=f"brief-{chat_id}",
            )
            reply = result.final_text or "(no briefing generated)"
        except Exception:
            logger.exception("Brief command failed")
            reply = "(error generating briefing)"

        if update.message:
            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i : i + 4000])

    return cmd_brief


def build_analytics_handler(*, db: Any) -> Any:
    """Build a /analytics handler with access to the logging DB."""

    async def cmd_analytics(update: Update, _ctx: Any) -> None:
        from cosinabox.agent.analytics import (
            get_cost_summary,
            get_error_summary,
            get_job_health,
            get_tool_stats,
        )

        cost = get_cost_summary(db)
        tools = get_tool_stats(db)
        jobs = get_job_health(db)
        errors = get_error_summary(db)

        lines = [
            f"Cost: ${cost['today']:.2f} today, ${cost['week_avg']:.2f}/day avg ({cost['days']}d)",
            f"Jobs: {jobs['runs_today']} runs today",
        ]
        if jobs["failing_jobs"]:
            lines.append("Failing: " + ", ".join(
                f"{j['name']} ({j['failures']}x)" for j in jobs["failing_jobs"]
            ))
        if tools["tools"]:
            lines.append("Top tools: " + ", ".join(
                f"{t['name']} ({t['calls']})" for t in tools["tools"][:3]
            ))
        if errors["errors"]:
            lines.append("Errors (24h): " + ", ".join(
                f"{e['type']} ({e['count']})" for e in errors["errors"]
            ))
        else:
            lines.append("Errors (24h): none")

        if update.message:
            await update.message.reply_text("\n".join(lines))

    return cmd_analytics
