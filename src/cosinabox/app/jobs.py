"""Job registration — core jobs and telegram-dependent jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cosinabox.agent.loop import AgentLoop
from cosinabox.jobs.base import Job
from cosinabox.scheduler.runner import SchedulerRunner

logger = logging.getLogger("cosinabox")


def register_core_jobs(
    scheduler: SchedulerRunner,
    jobs_config: dict[str, Any],
    *,
    gmail: Any,
    calendar: Any,
    loop: AgentLoop,
    personality: str,
    name: str,
    stakeholders: list[dict[str, Any]],
    event_relevance: dict[str, list[str]] | None = None,
    memory: Any | None = None,
    attio: Any | None = None,
    drive: Any | None = None,
    auth_health_db_path: Path | None = None,
    auth_health_account_emails: list[str] | None = None,
) -> None:
    """Register the 5 core scheduled jobs (no send_telegram dependency).

    Args:
        auth_health_db_path: when provided, AuthHealthJob persists per-account
            status to this SQLite DB after each tick. Read by /status.
        auth_health_account_emails: ordered list of Google account emails
            from integrations.yaml. Used as the email field in persisted rows.
    """
    from cosinabox.jobs.evening_wrap import EveningWrapJob
    from cosinabox.jobs.followup_reminder import FollowupReminderJob
    from cosinabox.jobs.morning_briefing import MorningBriefingJob
    from cosinabox.jobs.pre_meeting_prep import PreMeetingPrepJob
    from cosinabox.jobs.weekly_review import WeeklyReviewJob

    relevance_keywords = list((event_relevance or {}).get("keywords") or [])
    relevance_domains = list((event_relevance or {}).get("domains") or [])

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
                db=memory,
                attio=attio,
                drive=drive,
            )
            scheduler.add_job(job, cron=cfg["schedule"], timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cfg["schedule"])

        elif job_name == "evening_wrap" and cfg.get("schedule"):
            job = EveningWrapJob(
                gmail=gmail,
                agent_loop=loop,
                personality=personality,
                name_for_briefing=name,
                db=memory,
                drive=drive,
            )
            scheduler.add_job(job, cron=cfg["schedule"], timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cfg["schedule"])

        elif job_name == "pre_meeting_prep":
            job = PreMeetingPrepJob(
                calendar=calendar,
                agent_loop=loop,
                personality=personality,
                skip_titles=cfg.get("skip_if_calendar_title_matches", []),
                relevance_keywords=relevance_keywords,
                relevance_domains=relevance_domains,
            )
            cron = cfg.get("schedule", "*/5 * * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)

        elif job_name == "weekly_review" and cfg.get("schedule"):
            job = WeeklyReviewJob(
                gmail=gmail,
                calendar=calendar,
                agent_loop=loop,
                personality=personality,
                name_for_briefing=name,
                stakeholders=stakeholders,
                db=memory,
                drive=drive,
            )
            scheduler.add_job(job, cron=cfg["schedule"], timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cfg["schedule"])

        elif job_name == "followup_reminder":
            # Pass gmail so the job can check recent sent-mail to each
            # stakeholder's email — the yaml ``last_contact`` field rarely
            # auto-updates and would otherwise produce false-positive
            # "cooling" reminders for people you emailed yesterday.
            job = FollowupReminderJob(stakeholders=stakeholders, gmail=gmail)
            cron = cfg.get("schedule", "30 9 * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)

    # auth_health: always-on by default; registered outside the iteration loop
    # so existing user repos whose jobs.yaml predates this change still get
    # silent-failure protection.
    from cosinabox import defaults
    from cosinabox.jobs.auth_health import AuthHealthJob

    auth_health_cfg = jobs_config.get("auth_health", {})
    if auth_health_cfg.get("enabled", True):
        cron = auth_health_cfg.get("schedule", defaults.AUTH_HEALTH_DEFAULT_SCHEDULE)
        scheduler.add_job(
            AuthHealthJob(
                db_path=auth_health_db_path,
                account_emails=auth_health_account_emails,
            ),
            cron=cron,
            timezone=auth_health_cfg.get("timezone"),
        )
        logger.info("Registered auth_health at %s", cron)


def register_telegram_jobs(
    scheduler: SchedulerRunner,
    jobs_config: dict[str, Any],
    *,
    send_telegram: Any,
    gmail: Any,
    memory: Any,
    memory_client: Any,
    tool_instances: dict[str, Any],
    loop: AgentLoop,
    integrations: dict[str, Any],
    stakeholders: list[dict[str, Any]],
    rela_agent: Any,
    scheduling_ctx: Any | None,  # SchedulingContext or None
    anthropic_factory: Any,
    chat_id: str,
    event_relevance: dict[str, list[str]] | None = None,
) -> None:
    """Register jobs that need send_telegram (runs AFTER send_telegram exists)."""
    relevance_keywords = list((event_relevance or {}).get("keywords") or [])
    relevance_domains = list((event_relevance or {}).get("domains") or [])
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
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "crm_email_sync":
            from cosinabox.jobs.crm_email_sync import CrmEmailSyncJob

            job = CrmEmailSyncJob(
                gmail=gmail,
                attio=tool_instances.get("attio"),
            )
            cron = cfg.get("schedule", "45 17 * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "extract_fireflies":
            from cosinabox.jobs.extract_fireflies import ExtractFirefliesJob

            job = ExtractFirefliesJob(
                fireflies=tool_instances.get("fireflies"),
                memory_client=memory_client,
                db=memory,
                anthropic_client=anthropic_factory(),
                cost_tracker=loop.cost,
            )
            cron = cfg.get("schedule", "0 7 * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "extract_gmail":
            from cosinabox.jobs.extract_gmail import ExtractGmailJob

            job = ExtractGmailJob(
                gmail=gmail,
                memory_client=memory_client,
                db=memory,
                anthropic_client=anthropic_factory(),
                stakeholders=stakeholders,
                cost_tracker=loop.cost,
            )
            cron = cfg.get("schedule", "15 7 * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "post_meeting_debrief":
            from cosinabox.jobs.post_meeting_debrief import PostMeetingDebriefJob

            # Owner emails feed the matcher's "exclude self from overlap"
            # rule. Without this, every transcript the owner attended
            # would cross-match every other meeting. Source of truth is
            # integrations.google.accounts[].email; missing config means
            # "no owner exclusion" (matcher still requires time + at
            # least one of title/attendee, so the bot is safe but more
            # permissive).
            google_accounts = integrations.get("google", {}).get("accounts", [])
            owner_emails: list[str] = [
                str(a["email"]) for a in google_accounts if isinstance(a, dict) and a.get("email")
            ]

            job = PostMeetingDebriefJob(
                calendar=tool_instances.get("calendar"),
                fireflies=tool_instances.get("fireflies"),
                db=memory,
                send_fn=send_telegram,
                skip_titles=jobs_config.get("pre_meeting_prep", {}).get(
                    "skip_if_calendar_title_matches",
                    [],
                ),
                rela=rela_agent,
                relevance_keywords=relevance_keywords,
                relevance_domains=relevance_domains,
                owner_emails=owner_emails,
                memory=memory,
                dm_session=f"dm-{chat_id}",
            )
            cron = cfg.get("schedule", "*/5 * * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "scheduling_poll_check":
            from cosinabox.jobs.scheduling_poll_check import SchedulingPollCheckJob

            if scheduling_ctx is None:
                logger.warning(
                    "scheduling_poll_check enabled but scheduling_ctx not built; skipping",
                )
                continue
            job = SchedulingPollCheckJob(
                ctx=scheduling_ctx,
                send_fn=send_telegram,
            )
            cron = cfg.get("schedule", "*/30 * * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "rela_daily_scan":
            from cosinabox.jobs.rela_daily_scan import RelaDailyScanJob

            job = RelaDailyScanJob(
                rela=rela_agent,
                stakeholders=stakeholders,
            )
            cron = cfg.get("schedule", "50 7 * * *")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
