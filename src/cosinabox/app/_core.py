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
from cosinabox.app.chat import is_approval  # noqa: F401 — re-export + used in handle_message
from cosinabox.jobs.base import Job, JobContext
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
    # Tool auto-discovery from integrations
    # ------------------------------------------------------------------

    def _build_tools(
        self,
        integrations: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        """Build tool instances and handler dict from integrations.yaml.

        Returns ``(tool_instances, tool_handlers, auth_errors)``.
        ``auth_errors`` contains human-readable alert strings for each tool
        that failed to initialise (missing env var, OAuth refresh failure,
        etc.). The caller surfaces these via ``send_telegram`` once the bot
        is up — logs alone are invisible to a deployed agent's user
        (feedback_flag_oauth_failures).
        """
        tools: dict[str, Any] = {}
        errors: list[str] = []

        google_cfg = integrations.get("google", {})
        if google_cfg.get("enabled"):
            try:
                from cosinabox.tools.google.calendar import CalendarTool
                from cosinabox.tools.google.gmail import GmailTool

                tools["gmail"] = GmailTool()
                tools["calendar"] = CalendarTool()
                logger.info("Google tools loaded (Gmail + Calendar)")
            except Exception as exc:
                logger.warning(
                    "Google tools unavailable — check OAuth tokens",
                    exc_info=True,
                )
                errors.append(
                    f"Google (Gmail + Calendar) auth failed: {exc}. "
                    "Run `cosinabox auth google` to refresh tokens."
                )

        if integrations.get("fireflies", {}).get("enabled"):
            api_key = os.getenv("FIREFLIES_API_KEY")
            if not api_key:
                msg = (
                    "Fireflies enabled in integrations.yaml but "
                    "FIREFLIES_API_KEY not set in .env — skipping. "
                    "Meeting transcripts will be unavailable."
                )
                logger.warning(msg)
                errors.append(msg)
            else:
                try:
                    from cosinabox.tools.fireflies import FirefliesTool

                    tools["fireflies"] = FirefliesTool(api_key=api_key)
                    logger.info("Fireflies tool loaded")
                except Exception as exc:
                    logger.warning("Fireflies unavailable", exc_info=True)
                    errors.append(f"Fireflies init failed: {exc}")

        if integrations.get("web_search", {}).get("enabled"):
            api_key = os.getenv("SERPER_API_KEY")
            if not api_key:
                msg = (
                    "Web search enabled in integrations.yaml but "
                    "SERPER_API_KEY not set in .env — skipping. "
                    "Web search will be unavailable."
                )
                logger.warning(msg)
                errors.append(msg)
            else:
                try:
                    from cosinabox.tools.web_search import WebSearchTool

                    tools["web_search"] = WebSearchTool(api_key=api_key)
                    logger.info("Web search tool loaded")
                except Exception as exc:
                    logger.warning("Web search unavailable", exc_info=True)
                    errors.append(f"Web search init failed: {exc}")

        if integrations.get("attio", {}).get("enabled"):
            try:
                from cosinabox.tools.attio import AttioClient

                tools["attio"] = AttioClient()
                logger.info("Attio CRM tool loaded")
            except Exception as exc:
                logger.warning("Attio CRM unavailable", exc_info=True)
                errors.append(f"Attio CRM init failed: {exc}")

        return tools, {}, errors

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
                job: Job = MorningBriefingJob(
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
                cron = cfg.get("schedule", "*/5 * * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)

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
                    result: str = original(ctx or JobContext())
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

            registered_job.run = _wrap(orig, jname)  # type: ignore[method-assign]  # monkey-patching for telegram output

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
        scheduling_enabled = bool(
            jobs_config.get("scheduling_poll_check", {}).get("enabled")
            or "scheduling" in integrations
        )
        scheduling_ctx: dict[str, Any] | None = None
        if scheduling_enabled:
            scheduling_ctx = {
                "db": memory,
                "coordinator_ctx": {
                    "anthropic_client": _Anthropic(),
                    "cost_tracker": None,  # filled after loop is created
                    "bot": None,  # filled after tg_app is created
                    "gmail": tool_instances.get("gmail"),
                },
                "owner_name": name,
                "owner_timezone": timezone,
            }

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
            scheduling_ctx["coordinator_ctx"]["cost_tracker"] = loop.cost

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
        import httpx

        tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        def send_telegram(text: str) -> None:
            for i in range(0, len(text), 4000):
                httpx.post(
                    tg_url,
                    json={"chat_id": chat_id, "text": text[i : i + 4000]},
                )

        # --- Surface any auth / tool init failures collected at startup ---
        # Per feedback_flag_oauth_failures: never silently drop accounts.
        if auth_errors:
            alert_body = "\n\n".join(f"- {e}" for e in auth_errors)
            try:
                send_telegram(
                    f"[cosinabox startup] Integration auth issues detected:\n\n{alert_body}"
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to send auth-error alert via Telegram")

        # --- Register jobs that need send_telegram ---
        for job_name, cfg in jobs_config.items():
            if not cfg.get("enabled"):
                continue
            if job_name == "inbound_email_check":
                from cosinabox.jobs.inbound_email_check import InboundEmailCheckJob

                google_cfg = integrations.get("google", {})
                job: Job = InboundEmailCheckJob(
                    gmail=gmail,
                    db=memory,
                    send_alert=send_telegram,
                    urgent_senders=google_cfg.get("urgent_senders", []),
                    poll_interval_minutes=google_cfg.get("poll_interval_minutes", 5),
                )
                cron = cfg.get("schedule", "*/5 * * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "crm_email_sync":
                from cosinabox.jobs.crm_email_sync import CrmEmailSyncJob

                job = CrmEmailSyncJob(
                    gmail=gmail,
                    attio=tool_instances.get("attio"),
                )
                cron = cfg.get("schedule", "45 17 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "extract_fireflies":
                from cosinabox.jobs.extract_fireflies import ExtractFirefliesJob

                job = ExtractFirefliesJob(
                    fireflies=tool_instances.get("fireflies"),
                    memory_client=memory_client,
                    db=memory,
                    anthropic_client=_Anthropic(),
                    cost_tracker=loop.cost,
                )
                cron = cfg.get("schedule", "0 7 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "extract_gmail":
                from cosinabox.jobs.extract_gmail import ExtractGmailJob

                job = ExtractGmailJob(
                    gmail=gmail,
                    memory_client=memory_client,
                    db=memory,
                    anthropic_client=_Anthropic(),
                    stakeholders=stakeholders,
                    cost_tracker=loop.cost,
                )
                cron = cfg.get("schedule", "15 7 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "post_meeting_debrief":
                from cosinabox.jobs.post_meeting_debrief import PostMeetingDebriefJob

                job = PostMeetingDebriefJob(
                    calendar=calendar,
                    fireflies=tool_instances.get("fireflies"),
                    db=memory,
                    send_fn=send_telegram,
                    skip_titles=jobs_config.get("pre_meeting_prep", {}).get(
                        "skip_if_calendar_title_matches",
                        [],
                    ),
                    rela=rela_agent,
                )
                cron = cfg.get("schedule", "*/5 * * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "scheduling_poll_check":
                from cosinabox.jobs.scheduling_poll_check import SchedulingPollCheckJob

                if scheduling_ctx is None:
                    logger.warning(
                        "scheduling_poll_check enabled but scheduling_ctx not built; skipping",
                    )
                    continue
                job = SchedulingPollCheckJob(
                    db=scheduling_ctx["db"],
                    gmail=scheduling_ctx["coordinator_ctx"]["gmail"],
                    calendar=tool_instances.get("calendar"),
                    anthropic_client=scheduling_ctx["coordinator_ctx"]["anthropic_client"],
                    cost_tracker=scheduling_ctx["coordinator_ctx"]["cost_tracker"],
                    send_fn=send_telegram,
                )
                cron = cfg.get("schedule", "*/30 * * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)
            elif job_name == "rela_daily_scan":
                from cosinabox.jobs.rela_daily_scan import RelaDailyScanJob

                job = RelaDailyScanJob(
                    rela=rela_agent,
                    stakeholders=stakeholders,
                )
                cron = cfg.get("schedule", "50 7 * * *")
                scheduler.add_job(job, cron=cron)
                logger.info("Registered %s at %s", job_name, cron)

        self._wire_telegram_output(scheduler, send_telegram)

        # --- Start scheduler ---
        logger.info("Starting scheduler with %d jobs", len(scheduler._jobs))
        scheduler.start()

        # --- Telegram DM polling ---
        # Track tools that are pending approval per session, with timestamps
        # so we can evict stale entries (user walked away without responding).
        import threading as _threading
        import time as _time

        from telegram import Update
        from telegram.ext import Application, MessageHandler, filters

        # Track tools pending approval per session (may be multiple).
        # Value is (list_of_tool_names, timestamp) so we can evict stale
        # entries from abandoned sessions.
        _pending_tools: dict[str, tuple[list[str], float]] = {}
        _PENDING_TOOL_TTL_S = 300  # 5 minutes
        # The DM handler runs on the PTB async loop thread, while the sweep
        # can be called by the same handler mid-request; scheduling outreach
        # and agent loop errors may interleave. Protect all accesses.
        _pending_tools_lock = _threading.Lock()

        def _sweep_pending_tools() -> None:
            now = _time.time()
            with _pending_tools_lock:
                expired = [
                    sid for sid, (_, ts) in _pending_tools.items() if now - ts > _PENDING_TOOL_TTL_S
                ]
                for sid in expired:
                    del _pending_tools[sid]

        async def handle_message(update: Update, _ctx: Any) -> None:
            if update.message is None or update.message.text is None:
                return
            if update.effective_chat is None:
                return
            if str(update.effective_chat.id) != chat_id:
                return

            user_text = update.message.text
            session = f"dm-{update.effective_chat.id}"
            logger.info("DM: %s", user_text[:80])

            _sweep_pending_tools()

            # Check if this message is an approval for pending tools. Both
            # conditions (exact-match normalised phrase AND session has a
            # pending tool) are enforced by ``is_approval``.
            tool_names_to_grant: list[str] = []
            with _pending_tools_lock:
                has_pending = session in _pending_tools
                if has_pending and is_approval(user_text, has_pending_tool=True):
                    tool_names, _ts = _pending_tools.pop(session)
                    tool_names_to_grant = tool_names
            if tool_names_to_grant:
                from cosinabox.agent.policy import grant_temporary_approval

                for tool_name in tool_names_to_grant:
                    grant_temporary_approval(session, tool_name)
                    logger.info("User approved %s in %s", tool_name, session)

            blocked: list[str] = []
            try:
                result = loop.run(prompt=user_text, session_id=session)
                reply = result.final_text or "(no response)"
                blocked = [tc.name for tc in result.tool_calls if "APPROVAL REQUIRED" in tc.result]
            except Exception:
                logger.exception("Agent loop failed")
                reply = "(error processing message)"
            if blocked:
                with _pending_tools_lock:
                    _pending_tools[session] = (blocked, _time.time())

            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i : i + 4000])

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
            scheduling_ctx["coordinator_ctx"]["bot"] = SyncSchedulingBotAdapter(
                bot_token,
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
