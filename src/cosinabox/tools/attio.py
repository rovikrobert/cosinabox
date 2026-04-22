"""Attio CRM client — people records + Keep Warm custom-field layer."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "cosinabox[attio] extra is required. Run: pip install 'cosinabox[attio]'"
    ) from e

from cosinabox.defaults import KEEP_WARM_DEFAULT_CADENCE_DAYS

ATTIO_BASE_URL = "https://api.attio.com/v2"

logger = logging.getLogger(__name__)


class AttioError(Exception):
    pass


@dataclass
class KeepWarmPerson:
    """Typed view for a Keep Warm-flagged person.

    The ``note`` field carries RELATIONSHIP CONTEXT only — who they are,
    how you know them, what they care about, what makes this relationship
    current. No future-tense actions, no deadlines, no items owed. Those
    belong in the commitments table (see ``cosinabox.commitments``).
    """

    name: str
    record_id: str
    cadence_days: int
    note: str | None
    last_interaction: str | None
    days_since: int | None


class AttioClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        key = api_key or os.getenv("ATTIO_API_KEY")
        if not key:
            raise AttioError(
                "ATTIO_API_KEY env var is required. Set it or pass api_key= explicitly."
            )
        self._headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, **params: Any) -> Any:
        with httpx.Client() as client:
            resp = client.get(f"{ATTIO_BASE_URL}{path}", headers=self._headers, params=params)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        with httpx.Client() as client:
            resp = client.post(f"{ATTIO_BASE_URL}{path}", headers=self._headers, json=body)
            resp.raise_for_status()
            return resp.json()

    def _patch(self, path: str, body: dict[str, Any]) -> Any:
        with httpx.Client() as client:
            resp = client.patch(f"{ATTIO_BASE_URL}{path}", headers=self._headers, json=body)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Normalization — shared by all record-returning methods.
    # ------------------------------------------------------------------

    def _normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        values = record.get("values", {})

        def _first_value(key: str) -> Any:
            """Return the ``value`` of the first dict in a list field, or None.

            Attio fields are always lists of dicts. Corrupt shapes (strings
            instead of dicts, missing keys) fall back to None so Keep Warm
            extraction can't crash normalization.
            """
            items = values.get(key, [])
            if not items or not isinstance(items, list):
                return None
            first = items[0]
            if isinstance(first, dict):
                return first.get("value")
            return None

        def _first_str(key: str) -> str:
            v = _first_value(key)
            return str(v) if v is not None else ""

        # Name
        name_items = values.get("name", [])
        if name_items and isinstance(name_items, list):
            nobj = name_items[0] if isinstance(name_items[0], dict) else {}
            first = nobj.get("first_name") or nobj.get("value", "")
            last = nobj.get("last_name", "")
            name = f"{first} {last}".strip() if (first or last) else ""
        else:
            name = ""

        title = _first_str("job_title")
        company_items = values.get("primary_company", [])
        company = ""
        if company_items and isinstance(company_items, list):
            cobj = company_items[0] if isinstance(company_items[0], dict) else {}
            company = str(cobj.get("target_record", {}).get("name", "") or cobj.get("value", ""))

        role = f"{title} at {company}".strip() if title and company else title or company

        rec_id = record.get("id", {})
        resolved_id = rec_id.get("record_id") if isinstance(rec_id, dict) else rec_id or ""

        # Keep Warm custom fields. Missing ⇒ False / None (not flagged).
        kw_value = _first_value("keep_warm")
        keep_warm = bool(kw_value) if kw_value is not None else False

        cadence_value = _first_value("keep_warm_cadence_days")
        cadence: int | None
        try:
            cadence = int(cadence_value) if cadence_value is not None else None
        except (TypeError, ValueError):
            cadence = None

        note_value = _first_value("keep_warm_note")
        note = str(note_value) if note_value is not None else None

        last_interaction_value = _first_value("last_interaction")
        last_interaction = str(last_interaction_value) if last_interaction_value else None

        return {
            "id": resolved_id,
            "name": name,
            "role": role,
            "keep_warm": keep_warm,
            "keep_warm_cadence_days": cadence,
            "keep_warm_note": note,
            "last_interaction": last_interaction,
        }

    # ------------------------------------------------------------------
    # People CRUD
    # ------------------------------------------------------------------

    def list_people(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._post("/objects/people/records/query", {"limit": limit})
        result: list[dict[str, Any]] = [self._normalize(r) for r in data.get("data", [])]
        return result

    def get_person(self, name: str) -> dict[str, Any] | None:
        data = self._post(
            "/objects/people/records/query",
            {"filter": {"name": {"$str_contains": name}}, "limit": 1},
        )
        records = data.get("data", [])
        if not records:
            return None
        result: dict[str, Any] = self._normalize(records[0])
        return result

    def search_people(self, query: str) -> list[dict[str, Any]]:
        data = self._post(
            "/objects/people/records/query",
            {"filter": {"name": {"$str_contains": query}}},
        )
        result: list[dict[str, Any]] = [self._normalize(r) for r in data.get("data", [])]
        return result

    def update_person(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        data = self._patch(f"/objects/people/records/{record_id}", {"values": fields})
        result: dict[str, Any] = self._normalize(data.get("data", data))
        return result

    def create_person(self, fields: dict[str, Any]) -> dict[str, Any]:
        data = self._post("/objects/people/records", {"values": fields})
        result: dict[str, Any] = self._normalize(data.get("data", data))
        return result

    # ------------------------------------------------------------------
    # Keep Warm (ported from cos-agent 2026-04-20)
    # ------------------------------------------------------------------

    def _compute_days_since(self, iso_timestamp: str | None) -> int | None:
        """Whole-day count from ``iso_timestamp`` until now.

        Attio's ``last_interaction`` is typically an ISO-8601 string. Invalid
        or missing timestamps return None, which downstream uses as
        "unknown — never flag as overdue."
        """
        if not iso_timestamp:
            return None
        try:
            dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return max(0, delta.days)

    def list_keep_warm(self, *, limit: int = 200) -> list[KeepWarmPerson]:
        """All people flagged keep_warm=True, sorted most-overdue first.

        Uses an Attio server-side filter on the ``keep_warm`` attribute so
        curated folks aren't lost to list_people pagination.
        Returns empty list on API errors (logged) — never raises.
        """
        try:
            data = self._post(
                "/objects/people/records/query",
                {"limit": limit, "filter": {"keep_warm": True}},
            )
        except Exception:
            logger.warning("list_keep_warm: Attio query failed", exc_info=True)
            return []

        people: list[KeepWarmPerson] = []
        for raw in data.get("data", []):
            normalized = self._normalize(raw)
            if not normalized.get("keep_warm"):
                # defense-in-depth: server-side filter should already gate this
                continue
            cadence = normalized.get("keep_warm_cadence_days") or KEEP_WARM_DEFAULT_CADENCE_DAYS
            last = normalized.get("last_interaction")
            people.append(
                KeepWarmPerson(
                    name=normalized.get("name", ""),
                    record_id=str(normalized.get("id") or ""),
                    cadence_days=int(cadence),
                    note=normalized.get("keep_warm_note"),
                    last_interaction=last,
                    days_since=self._compute_days_since(last),
                )
            )

        # Sort most overdue first; unknown (None days_since) sorts last.
        people.sort(
            key=lambda p: (p.days_since is None, -(p.days_since or 0)),
        )
        return people

    def get_keep_warm_overdue(self) -> list[KeepWarmPerson]:
        """Keep Warm people whose days_since > their cadence.

        Unknown (``days_since is None``) is never flagged — we can't
        distinguish "never contacted" from "no data synced to Attio yet."
        """
        return [
            p
            for p in self.list_keep_warm()
            if p.days_since is not None and p.days_since > p.cadence_days
        ]

    def set_keep_warm(
        self,
        *,
        person: str,
        cadence_days: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Mark a person Keep Warm with a per-person cadence.

        Cadence is clamped to [1, 365] to prevent obvious typos.

        The returned dict includes ``prior_note`` — the ``keep_warm_note``
        value that was on the record before the PATCH landed — so callers
        can snapshot-on-write without issuing a second GET.
        """
        profile = self.get_person(person)
        if not profile:
            return {"status": "error", "message": f"Person '{person}' not found in Attio."}
        record_id = str(profile.get("id") or "")
        if not record_id:
            return {"status": "error", "message": f"Person '{person}' has no record id."}
        prior_note = profile.get("keep_warm_note")

        clamped = max(1, min(365, int(cadence_days)))
        fields: dict[str, Any] = {
            "keep_warm": [{"value": True}],
            "keep_warm_cadence_days": [{"value": clamped}],
        }
        if note is not None:
            fields["keep_warm_note"] = [{"value": note}]

        try:
            self._patch(f"/objects/people/records/{record_id}", {"values": fields})
        except Exception as exc:
            logger.warning("set_keep_warm failed for %s", person, exc_info=True)
            return {"status": "error", "message": f"Attio update failed: {exc}"}

        logger.info("keep_warm set: person=%s cadence=%d", person, clamped)
        return {
            "status": "ok",
            "record_id": record_id,
            "person": person,
            "cadence_days": clamped,
            "prior_note": prior_note,
        }

    def unset_keep_warm(
        self,
        *,
        person: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Remove a person from Keep Warm. Clears cadence; note is optional."""
        profile = self.get_person(person)
        if not profile:
            return {"status": "error", "message": f"Person '{person}' not found in Attio."}
        record_id = str(profile.get("id") or "")
        if not record_id:
            return {"status": "error", "message": f"Person '{person}' has no record id."}

        fields: dict[str, Any] = {
            "keep_warm": [{"value": False}],
            "keep_warm_cadence_days": [],
        }
        if note is not None:
            fields["keep_warm_note"] = [{"value": note}]

        try:
            self._patch(f"/objects/people/records/{record_id}", {"values": fields})
        except Exception as exc:
            logger.warning("unset_keep_warm failed for %s", person, exc_info=True)
            return {"status": "error", "message": f"Attio update failed: {exc}"}

        logger.info("keep_warm unset: person=%s", person)
        return {"status": "ok", "record_id": record_id, "person": person}
