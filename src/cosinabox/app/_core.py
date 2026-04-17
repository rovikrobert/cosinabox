"""Top-level App — wires config, tools, scheduler, and Telegram."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from cosinabox import defaults
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router
from cosinabox.prompts.core import render_system_prompt
from cosinabox.scheduler.runner import SchedulerRunner
from cosinabox.stakeholders import get_stakeholders

logger = logging.getLogger("cosinabox")


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
    # Config loading (delegators — logic lives in app.config)
    # ------------------------------------------------------------------

    def _load_personality(self) -> tuple[str, str, str]:
        """Returns (body, name, timezone)."""
        from cosinabox.app.config import load_personality

        return load_personality(self.config_dir)

    def _load_jobs(self) -> dict[str, Any]:
        from cosinabox.app.config import load_jobs

        return load_jobs(self.config_dir)

    def _load_integrations(self) -> dict[str, Any]:
        from cosinabox.app.config import load_integrations

        return load_integrations(self.config_dir)

    # ------------------------------------------------------------------
    # Tool auto-discovery (delegator — logic lives in app.tools)
    # ------------------------------------------------------------------

    def _build_tools(
        self,
        integrations: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        from cosinabox.app.tools import build_tools

        return build_tools(integrations)

    # ------------------------------------------------------------------
    # Job registration (delegator — logic lives in app.jobs)
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
        from cosinabox.app.jobs import register_core_jobs

        register_core_jobs(
            scheduler,
            jobs_config,
            gmail=gmail,
            calendar=calendar,
            loop=loop,
            personality=personality,
            name=name,
            stakeholders=stakeholders,
        )

    # ------------------------------------------------------------------
    # Telegram output wiring (delegator — logic lives in app.alerts)
    # ------------------------------------------------------------------

    @staticmethod
    def _wire_telegram_output(scheduler: SchedulerRunner, send_fn: Any) -> None:
        from cosinabox.app.alerts import wire_telegram_output

        wire_telegram_output(scheduler, send_fn)

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

        # Set runtime timezone from personality.md — scheduler uses this
        from cosinabox.timezone import set_timezone

        set_timezone(timezone)
        logger.info("Timezone set to %s", timezone)

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
        tool_instances, _, auth_errors = self._build_tools(integrations)
        stakeholders = get_stakeholders(config_dir=self.config_dir, integrations=integrations)

        system_prompt = render_system_prompt(
            personality=personality,
            name=name,
            timezone=timezone,
        )

        from anthropic import Anthropic as _Anthropic

        from cosinabox.memory import Memory
        from cosinabox.tools.registry import build_tool_registry

        # Conversation memory (SQLite in user's config dir)
        memory = Memory(db_path=self.config_dir / ".cosinabox" / "memory.db")

        # --- Memory client (for extraction + Rela) ---
        from cosinabox.memory.client import resolve_memory_client

        memory_client = resolve_memory_client(
            db_path=self.config_dir / ".cosinabox" / "memory.db",
        )

        # --- Scheduling context (built once; shared by tool registry + poll job) ---
        # Built lazily so the scheduling job + tools only wire if the user has
        # opted in (via scheduling_poll_check in jobs.yaml OR a scheduling:
        # section in integrations.yaml). OSS users without either get no extra
        # cost or surface area.
        from cosinabox.scheduling.context import SchedulingContext, build_from_integrations

        scheduling_enabled = bool(
            jobs_config.get("scheduling_poll_check", {}).get("enabled")
            or "scheduling" in integrations
        )
        scheduling_ctx: SchedulingContext | None = None
        if scheduling_enabled:
            # Build a CalendarProvider if a calendar tool exists.
            cal_provider = None
            if "calendar" in tool_instances:
                from cosinabox.tools.google.calendar import GoogleCalendarProvider

                cal_provider = GoogleCalendarProvider(tool_instances["calendar"])

            scheduling_ctx = build_from_integrations(
                db=memory,
                owner_name=name,
                owner_timezone=timezone,
                calendar=cal_provider,
                gmail=tool_instances.get("gmail"),
                anthropic_client=_Anthropic(),
                # cost_tracker + bot filled after loop/tg_app are created
            )

        # Initial tool registry (without rela_query — loop not yet created)
        tool_definitions, tool_handlers = build_tool_registry(
            tool_instances,
            timezone=timezone,
            scheduling_ctx=scheduling_ctx,
        )

        loop = AgentLoop(
            anthropic_client=_Anthropic(),
            router=Router(),
            cost_tracker=CostTracker(
                per_message_cap_usd=defaults.COST_PER_MESSAGE_CAP_USD,
                daily_cap_usd=defaults.COST_DAILY_CAP_USD,
                db=memory,
            ),
            tools=tool_handlers,
            tool_definitions=tool_definitions,
            memory=memory,
            max_tool_iterations=defaults.MAX_TOOL_ITERATIONS,
            tool_iteration_delay_s=defaults.TOOL_ITERATION_DELAY_S,
            system_prompt=system_prompt,
        )

        # Rela agent (created after loop so it can use it; needs to be wired
        # back into the loop's tool registry so rela_query is available in DMs)
        rela_agent = None
        if any(
            jobs_config.get(j, {}).get("enabled")
            for j in ("post_meeting_debrief", "rela_daily_scan")
        ):
            from cosinabox.agent.rela import create_rela_agent

            rela_cfg = integrations.get("rela", {}) or {}
            max_ingests = rela_cfg.get("max_concurrent_ingests")
            rela_agent = create_rela_agent(
                agent_loop=loop,
                memory_client=memory_client,
                max_concurrent_ingests=max_ingests,
            )

        # Now that the loop (and its cost tracker) exists, plug it into the
        # scheduling context so tool handlers + the poll job share one tracker.
        if scheduling_ctx is not None:
            scheduling_ctx = scheduling_ctx.replace(cost_tracker=loop.cost)

        tool_definitions, tool_handlers = build_tool_registry(
            tool_instances,
            timezone=timezone,
            rela_agent=rela_agent,
            scheduling_ctx=scheduling_ctx,
        )
        # Patch updated registry into the already-constructed loop
        loop.tools = tool_handlers
        loop.tool_definitions = tool_definitions

        # --- Scheduler ---
        # Set the operating timezone from personality.md BEFORE creating
        # the scheduler, so cron expressions fire in the user's local time.
        from cosinabox.timezone import set_timezone

        try:
            set_timezone(timezone)
            logger.info("Scheduler timezone set to %s", timezone)
        except KeyError:
            logger.warning(
                "Invalid timezone %r in personality.md — falling back to %s",
                timezone,
                defaults.DEFAULT_TIMEZONE,
            )

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
        from cosinabox.app.alerts import make_send_telegram, send_auth_error_alert

        send_telegram = make_send_telegram(bot_token, chat_id)
        send_auth_error_alert(send_telegram, auth_errors)

        # --- Register jobs that need send_telegram ---
        from cosinabox.app.jobs import register_telegram_jobs

        register_telegram_jobs(
            scheduler,
            jobs_config,
            send_telegram=send_telegram,
            gmail=gmail,
            memory=memory,
            memory_client=memory_client,
            tool_instances=tool_instances,
            loop=loop,
            integrations=integrations,
            stakeholders=stakeholders,
            rela_agent=rela_agent,
            scheduling_ctx=scheduling_ctx,
            anthropic_factory=_Anthropic,
        )

        self._wire_telegram_output(scheduler, send_telegram)

        # --- Start scheduler ---
        logger.info("Starting scheduler with %d jobs", len(scheduler._jobs))
        scheduler.start()

        # --- Telegram DM polling ---
        from telegram.ext import Application, MessageHandler, filters

        from cosinabox.app.chat import build_dm_handler

        handle_message = build_dm_handler(loop, chat_id)

        tg_app = Application.builder().token(bot_token).build()
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # --- Scheduling callback handler (inline buttons on poll DMs) ---
        if scheduling_ctx is not None:
            from telegram.ext import CallbackQueryHandler

            from cosinabox.bot.scheduling_callbacks import (
                build_scheduling_callback_handler,
            )
            from cosinabox.bot.sync_scheduling_adapter import (
                SyncSchedulingBotAdapter,
            )

            sched_cb = build_scheduling_callback_handler(memory)
            tg_app.add_handler(
                CallbackQueryHandler(sched_cb, pattern=r"^sched_resp:"),
            )
            # Outreach runs in sync worker threads; python-telegram-bot's
            # Application.bot is async and has an incompatible send_poll
            # signature, so wire the sync HTTP adapter instead.
            scheduling_ctx = scheduling_ctx.replace(
                bot=SyncSchedulingBotAdapter(bot_token),
            )

        # --- Bot commands ---
        from telegram.ext import CommandHandler

        from cosinabox.bot.commands import (
            build_analytics_handler,
            build_brief_handler,
            build_cost_handler,
            build_status_handler,
            cmd_help,
        )

        tg_app.add_handler(CommandHandler("help", cmd_help))
        tg_app.add_handler(CommandHandler("start", cmd_help))
        tg_app.add_handler(
            CommandHandler(
                "status",
                build_status_handler(
                    name=name,
                    timezone=timezone,
                    tool_definitions=tool_definitions,
                    jobs_config=jobs_config,
                    stakeholder_count=len(stakeholders),
                ),
            )
        )
        tg_app.add_handler(
            CommandHandler(
                "cost",
                build_cost_handler(
                    cost_tracker=loop.cost,
                ),
            )
        )
        tg_app.add_handler(
            CommandHandler(
                "brief",
                build_brief_handler(
                    agent_loop=loop,
                    chat_id=chat_id,
                ),
            )
        )
        tg_app.add_handler(
            CommandHandler(
                "analytics",
                build_analytics_handler(
                    db=memory,
                ),
            )
        )

        logger.info(
            "cosinabox running: %s's CoS (%s)",
            name,
            timezone,
        )
        tg_app.run_polling(drop_pending_updates=True)
