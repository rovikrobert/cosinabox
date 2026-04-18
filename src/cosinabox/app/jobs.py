"""Job registration — core jobs and telegram-dependent jobs."""

from __future__ import annotations

import logging
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
) -> None:
    """Register the 5 core scheduled jobs (no send_telegram dependency)."""
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
) -> None:
    """Register jobs that need send_telegram (runs AFTER send_telegram exists)."""
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
                anthropic_client=anthropic_factory(),
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
                anthropic_client=anthropic_factory(),
                stakeholders=stakeholders,
                cost_tracker=loop.cost,
            )
            cron = cfg.get("schedule", "15 7 * * *")
            scheduler.add_job(job, cron=cron)
            logger.info("Registered %s at %s", job_name, cron)
        elif job_name == "post_meeting_debrief":
            from cosinabox.jobs.post_meeting_debrief import PostMeetingDebriefJob

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
                memory=memory,
                dm_session=f"dm-{chat_id}",
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
                ctx=scheduling_ctx,
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
