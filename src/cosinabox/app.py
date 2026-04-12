"""Top-level App — wires config, tools, scheduler, and Telegram."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from cosinabox import defaults
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router
from cosinabox.jobs.base import JobContext
from cosinabox.prompts.core import render_system_prompt
from cosinabox.scheduler.runner import SchedulerRunner
from cosinabox.stakeholders import get_stakeholders

logger = logging.getLogger("cosinabox")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


class App:
    """Compose personality + stakeholders + jobs and run the bot + scheduler.

    Usage::

        from cosinabox import App
        App().run()

    Reads config from the current directory (or ``config_dir``):
    ``personality.md``, ``jobs.yaml``, ``integrations.yaml``,
    ``stakeholders.yaml``, and ``.env``.
    """

    def __init__(self, config_dir: str | None = None) -> None:
        self.config_dir = Path(config_dir or os.getcwd())

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_personality(self) -> tuple[str, str, str]:
        """Returns (body, name, timezone)."""
        path = self.config_dir / "personality.md"
        if not path.exists():
            logger.warning("personality.md not found in %s", self.config_dir)
            return "(no personality)", "user", defaults.DEFAULT_TIMEZONE
        text = path.read_text()
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return text, "user", defaults.DEFAULT_TIMEZONE
        front: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
        return (
            m.group(2).strip(),
            front.get("name", "user"),
            front.get("timezone", defaults.DEFAULT_TIMEZONE),
        )

    def _load_jobs(self) -> dict[str, Any]:
        path = self.config_dir / "jobs.yaml"
        if not path.exists():
            logger.warning("jobs.yaml not found in %s", self.config_dir)
            return {}
        data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return data.get("jobs", {})

    def _load_integrations(self) -> dict[str, Any]:
        path = self.config_dir / "integrations.yaml"
        if not path.exists():
            return {}
        data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return data.get("integrations", {})

    # ------------------------------------------------------------------
    # Tool auto-discovery from integrations
    # ------------------------------------------------------------------

    def _build_tools(self, integrations: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build tool instances and handler dict from integrations.yaml.

        Returns (tool_instances, tool_handlers).
        tool_instances: {"gmail": GmailTool, "calendar": CalendarTool, ...}
        tool_handlers: {} (empty for now — tools wired as agent functions later)
        """
        tools: dict[str, Any] = {}

        google_cfg = integrations.get("google", {})
        if google_cfg.get("enabled"):
            try:
                from cosinabox.tools.google.calendar import CalendarTool
                from cosinabox.tools.google.gmail import GmailTool

                tools["gmail"] = GmailTool()
                tools["calendar"] = CalendarTool()
                logger.info("Google tools loaded (Gmail + Calendar)")
            except Exception:
                logger.warning(
                    "Google tools unavailable — check OAuth tokens",
                    exc_info=True,
                )

        if integrations.get("fireflies", {}).get("enabled"):
            try:
                from cosinabox.tools.fireflies import FirefliesTool

                tools["fireflies"] = FirefliesTool()
                logger.info("Fireflies tool loaded")
            except Exception:
                logger.warning("Fireflies unavailable", exc_info=True)

        if integrations.get("web_search", {}).get("enabled"):
            try:
                from cosinabox.tools.web_search import WebSearchTool

                tools["web_search"] = WebSearchTool()
                logger.info("Web search tool loaded")
            except Exception:
                logger.warning("Web search unavailable", exc_info=True)

        if integrations.get("attio", {}).get("enabled"):
            try:
                from cosinabox.tools.attio import AttioClient

                tools["attio"] = AttioClient()
                logger.info("Attio CRM tool loaded")
            except Exception:
                logger.warning("Attio CRM unavailable", exc_info=True)

        return tools, {}

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def _register_jobs(
        self,
        scheduler: SchedulerRunner,
        jobs_config: dict[str, Any],
        *,
        gmail: Any,
        calendar: Any,
        loop: AgentLoop,
        personality: str,
        name: str,
        stakeholders: list[dict[str, Any]],
    ) -> None:
        from cosinabox.jobs.evening_wrap import EveningWrapJob
        from cosinabox.jobs.followup_reminder import FollowupReminderJob
        from cosinabox.jobs.morning_briefing import MorningBriefingJob
        from cosinabox.jobs.pre_meeting_prep import PreMeetingPrepJob
        from cosinabox.jobs.weekly_review import WeeklyReviewJob

        for job_name, cfg in jobs_config.items():
            if not cfg.get("enabled"):
                continue

            if job_name == "morning_briefing" and cfg.get("schedule"):
                job = MorningBriefingJob(
                    gmail=gmail,
                    calendar=calendar,
                    agent_loop=loop,
                    personality=personality,
                    name_for_briefing=name,
                    stakeholders=stakeholders,
                )
                scheduler.add_job(job, cron=cfg["schedule"])
                logger.info("Registered %s at %s", job_name, cfg["schedule"])

            elif job_name == "evening_wrap" and cfg.get("schedule"):
                job = EveningWrapJob(
                    gmail=gmail,
                    agent_loop=loop,
                    personality=personality,
                    name_for_briefing=name,
                )
                scheduler.add_job(job, cron=cfg["schedule"])
                logger.info("Registered %s at %s", job_name, cfg["schedule"])

            elif job_name == "pre_meeting_prep":
                job = PreMeetingPrepJob(
                    calendar=calendar,
                    agent_loop=loop,
                    personality=personality,
                    skip_titles=cfg.get("skip_if_calendar_title_matches", []),
                )
                scheduler.add_job(job, cron="*/5 * * * *")
                logger.info("Registered %s (every 5 min)", job_name)

            elif job_name == "weekly_review" and cfg.get("schedule"):
                job = WeeklyReviewJob(
                    gmail=gmail,
                    calendar=calendar,
                    agent_loop=loop,
                    personality=personality,
                    name_for_briefing=name,
                    stakeholders=stakeholders,
                )
                scheduler.add_job(job, cron=cfg["schedule"])
                logger.info("Registered %s at %s", job_name, cfg["schedule"])

            elif job_name == "followup_reminder":
                job = FollowupReminderJob(stakeholders=stakeholders)
                cron = cfg.get("schedule", "30 9 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)

    # ------------------------------------------------------------------
    # Telegram output wiring
    # ------------------------------------------------------------------

    @staticmethod
    def _wire_telegram_output(scheduler: SchedulerRunner, send_fn: Any) -> None:
        """Wrap each job's run() to send output to Telegram."""
        NO_OP = ("no upcoming", "no events", "no meetings", "(no ")

        for jname, registered_job in scheduler._jobs.items():
            orig = registered_job.run

            def _wrap(original: Any, name: str) -> Any:
                def wrapped(ctx: JobContext | None = None) -> str:
                    result = original(ctx or JobContext())
                    if not result or not result.strip():
                        return result
                    if any(m in result.lower() for m in NO_OP):
                        return result
                    try:
                        send_fn(f"[{name}]\n\n{result}")
                    except Exception:
                        logger.exception("Telegram send failed for %s", name)
                    return result

                return wrapped

            registered_job.run = _wrap(orig, jname)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the bot + scheduler. Blocks until SIGTERM/SIGINT."""
        load_dotenv(self.config_dir / ".env")

        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )

        # --- Validate required config ---
        personality, name, timezone = self._load_personality()
        jobs_config = self._load_jobs()
        integrations = self._load_integrations()

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not bot_token or not chat_id:
            logger.error(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env. "
                "See docs/agent/persona-interview.md step 7."
            )
            raise SystemExit(1)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.error(
                "ANTHROPIC_API_KEY must be set in .env. Get one at https://console.anthropic.com/"
            )
            raise SystemExit(1)

        # --- Build components ---
        tool_instances, _ = self._build_tools(integrations)
        stakeholders = get_stakeholders(config_dir=self.config_dir, integrations=integrations)

        system_prompt = render_system_prompt(
            personality=personality,
            name=name,
            timezone=timezone,
        )

        from anthropic import Anthropic

        from cosinabox.tools.registry import build_tool_registry

        tool_definitions, tool_handlers = build_tool_registry(
            tool_instances, timezone=timezone,
        )

        loop = AgentLoop(
            anthropic_client=Anthropic(),
            router=Router(),
            cost_tracker=CostTracker(
                per_message_cap_usd=defaults.COST_PER_MESSAGE_CAP_USD,
                daily_cap_usd=defaults.COST_DAILY_CAP_USD,
            ),
            tools=tool_handlers,
            tool_definitions=tool_definitions,
            max_tool_iterations=defaults.MAX_TOOL_ITERATIONS,
            tool_iteration_delay_s=defaults.TOOL_ITERATION_DELAY_S,
            system_prompt=system_prompt,
        )

        # --- Scheduler ---
        scheduler = SchedulerRunner()
        gmail = tool_instances.get("gmail")
        calendar = tool_instances.get("calendar")

        self._register_jobs(
            scheduler,
            jobs_config,
            gmail=gmail,
            calendar=calendar,
            loop=loop,
            personality=personality,
            name=name,
            stakeholders=stakeholders,
        )

        # --- Telegram ---
        import httpx

        tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        def send_telegram(text: str) -> None:
            for i in range(0, len(text), 4000):
                httpx.post(
                    tg_url,
                    json={"chat_id": chat_id, "text": text[i : i + 4000]},
                )

        self._wire_telegram_output(scheduler, send_telegram)

        # --- Start scheduler ---
        logger.info("Starting scheduler with %d jobs", len(scheduler._jobs))
        scheduler.start()

        # --- Telegram DM polling ---
        from telegram import Update
        from telegram.ext import Application, MessageHandler, filters

        async def handle_message(update: Update, _ctx: Any) -> None:
            if update.message is None or update.message.text is None:
                return
            if str(update.effective_chat.id) != chat_id:
                return

            user_text = update.message.text
            logger.info("DM: %s", user_text[:80])

            try:
                result = loop.run(
                    prompt=user_text,
                    session_id=f"dm-{update.effective_chat.id}",
                )
                reply = result.final_text or "(no response)"
            except Exception:
                logger.exception("Agent loop failed")
                reply = "(error processing message)"

            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i : i + 4000])

        tg_app = Application.builder().token(bot_token).build()
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info(
            "cosinabox running: %s's CoS (%s)",
            name,
            timezone,
        )
        tg_app.run_polling(drop_pending_updates=True)
