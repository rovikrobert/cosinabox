"""Participant resolution — timezone and channel routing.

Ported from cos-agent/src/scheduling/participant.py.
OSS adaptation: no hardcoded domain/org → timezone mappings. Users
provide their own via integrations.yaml `scheduling.domain_timezones`.
"""

from __future__ import annotations


def resolve_timezone(
    *,
    email: str | None,
    org: str | None,
    explicit_tz: str | None,
    default_tz: str,
    domain_map: dict[str, str] | None = None,
    org_map: dict[str, str] | None = None,
) -> str:
    """Resolve a participant's timezone.

    Resolution order (first match wins):
    1. Explicit timezone if set (and not equal to default)
    2. Organisation name match against `org_map` (case-insensitive substring)
    3. Email domain match against `domain_map` (exact or subdomain)
    4. Fall back to `default_tz`
    """
    if explicit_tz and explicit_tz != default_tz:
        return explicit_tz

    if org and org_map:
        org_lower = org.lower()
        for key, tz in org_map.items():
            if key.lower() in org_lower:
                return tz

    if email and domain_map and "@" in email:
        domain = email.split("@")[-1].lower()
        for key, tz in domain_map.items():
            key_lower = key.lower()
            if domain == key_lower or domain.endswith(f".{key_lower}"):
                return tz

    return default_tz


def resolve_channel(*, email: str | None, telegram_id: str | None) -> str:
    """Pick the outreach channel for a participant.

    Priority:
    1. Telegram if `telegram_id` set
    2. Gmail otherwise (even if email is None — coordinator logs a warning)
    """
    if telegram_id:
        return "telegram"
    return "gmail"
