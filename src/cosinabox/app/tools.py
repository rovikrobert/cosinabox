"""Tool auto-discovery from integrations.yaml."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("cosinabox")


def build_tools(
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
