"""Weekly research digest: collect -> classify -> synthesize -> store -> notify."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.memory.backup import backup_database
from cosinabox.research.alerts import synthesis_alerts
from cosinabox.research.classifier import classify
from cosinabox.research.collector import collect
from cosinabox.research.config import ResearchConfig

# Imported at module scope, not inside run(): the tests patch
# `cosinabox.jobs.research_digest.synthesize`, which requires it to be a
# module attribute.
from cosinabox.research.synthesizer import synthesize

logger = logging.getLogger(__name__)

_DEDUP_TTL_DAYS = 30
_DEDUP_CAP = 150


class ResearchDigestJob(Job):
    name = "research_digest"

    def __init__(
        self,
        *,
        config_dir: Path,
        db: Any,
        anthropic_client: Any,
        search_api_key: str,
        send_telegram: Callable[[str], Any],
        notify_error: Callable[[str], Any],
        model: str,
    ) -> None:
        self.config_dir = config_dir
        self.db = db
        self.client = anthropic_client
        self.search_api_key = search_api_key
        self.send_telegram = send_telegram
        self.notify_error = notify_error
        self.model = model

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _week_of(self) -> str:
        """Monday of the current week, as an ISO date."""
        today = self._now().date()
        return (today - timedelta(days=today.weekday())).isoformat()

    def run(self, context: JobContext) -> str:
        cfg = ResearchConfig.load(self.config_dir / "research.yaml")
        if cfg is None or not cfg.groups:
            return "research_digest not configured (no research.yaml) — skipped."
        if not self.search_api_key:
            return "research_digest not configured (no search API key) — skipped."

        try:
            from cosinabox.research.feeds import read_feeds
            from cosinabox.tools.tavily import TavilyTool
        except ImportError:
            return (
                "research_digest not configured: install the extra with "
                "`pip install 'cosinabox[research]'` — skipped."
            )

        week_of = self._week_of()

        # Back up before writing. The signals table is primary data and lives
        # on one volume; this is the cheapest insurance available.
        db_path = getattr(self.db, "db_path", None)
        if db_path:
            try:
                backup_database(Path(db_path), now=self._now())
            except Exception as exc:
                logger.warning("Pre-run backup failed: %s", exc)

        search = TavilyTool(api_key=self.search_api_key).search
        result = collect(
            cfg,
            search=search,
            feed_reader=lambda feeds: read_feeds(feeds, now=self._now()),
        )
        if result.search_failed:
            self.notify_error("research_digest: every search query failed — no digest this week.")
            return "research_digest: search failed, no candidates collected."
        if not result.items:
            self.notify_error("research_digest: collection produced no candidates.")
            return "research_digest: no candidates collected."

        items = classify(result.items, entity_names=cfg.entity_names(), client=self.client)

        dedup_index = self.db.load_research_dedup(
            now=self._now(), ttl_days=_DEDUP_TTL_DAYS, cap=_DEDUP_CAP
        )

        parsed, raw = synthesize(
            cfg,
            items=items,
            dedup_index=dedup_index,
            week_of=week_of,
            client=self.client,
            model=self.model,
        )

        signals = parsed.get("signal_records") or []
        written = self.db.save_research_signals(signals, week_of=week_of)
        self.db.save_research_dedup(
            [
                {"url": s.get("source_url", ""), "headline": s.get("headline", "")}
                for s in signals
                if isinstance(s, dict)
            ],
            week_of=week_of,
        )

        summary = parsed.get("telegram_summary") or ""
        if summary:
            self.send_telegram(summary)

        # "The job ran" is not success — check the output before declaring it.
        for alert in synthesis_alerts(
            telegram_summary=summary,
            signal_count=len(signals),
            raw_length=len(raw),
        ):
            self.notify_error(f"research_digest: {alert}")

        return (
            f"research_digest for week of {week_of}: "
            f"{len(items)} candidates, {written} signal(s) stored."
        )
