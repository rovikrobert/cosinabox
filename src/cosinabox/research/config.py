"""Loader for `research.yaml` — turns user config into queries and filters.

The legacy implementation hardcoded its targets in two Python modules, which
made the pipeline unusable by anyone else. Everything the pipeline needs to
know about *what* to track now comes from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cosinabox import defaults

# Field-level queries have no owning group. They sort after every real group so
# a broad trend query can never displace a targeted one under the result cap.
_FIELD_GROUP = "field"
_FIELD_PRIORITY = 10_000


@dataclass(frozen=True)
class SearchSpec:
    country: str = defaults.RESEARCH_SEARCH_COUNTRY
    topic: str = defaults.RESEARCH_SEARCH_TOPIC
    time_range: str | None = None
    results_per_query: int = defaults.RESEARCH_RESULTS_PER_QUERY

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SearchSpec:
        raw = raw or {}
        return cls(
            country=str(raw.get("country", defaults.RESEARCH_SEARCH_COUNTRY)),
            topic=str(raw.get("topic", defaults.RESEARCH_SEARCH_TOPIC)),
            time_range=raw.get("time_range"),
            results_per_query=int(
                raw.get("results_per_query", defaults.RESEARCH_RESULTS_PER_QUERY)
            ),
        )


@dataclass(frozen=True)
class Entity:
    name: str
    aliases: tuple[str, ...] = ()
    queries: tuple[str, ...] = ()


@dataclass(frozen=True)
class Group:
    name: str
    priority: int
    search: SearchSpec
    entities: tuple[Entity, ...]


@dataclass(frozen=True)
class Query:
    text: str
    group: str
    priority: int
    search: SearchSpec


@dataclass(frozen=True)
class ResearchConfig:
    groups: tuple[Group, ...]
    feeds: tuple[str, ...]
    field_queries: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> ResearchConfig | None:
        """Parse `research.yaml`. Returns None when the file does not exist.

        Absence is a normal state — the file is opt-in — so the caller reports
        "not configured" rather than crashing the scheduler.
        """
        if not path.exists():
            return None
        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        groups: list[Group] = []
        for g in raw.get("groups") or []:
            entities = tuple(
                Entity(
                    name=str(e["name"]),
                    aliases=tuple(str(a) for a in (e.get("aliases") or [])),
                    queries=tuple(str(q) for q in (e.get("queries") or [])),
                )
                for e in (g.get("entities") or [])
                if e.get("name")
            )
            groups.append(
                Group(
                    name=str(g["name"]),
                    priority=int(g["priority"]),
                    search=SearchSpec.from_dict(g.get("search")),
                    entities=entities,
                )
            )
        return cls(
            groups=tuple(groups),
            feeds=tuple(str(f) for f in (raw.get("feeds") or [])),
            field_queries=tuple(str(q) for q in (raw.get("field_queries") or [])),
        )

    def queries(self) -> list[Query]:
        """Flatten every entity query, then the field queries, into one list."""
        out: list[Query] = []
        for group in self.groups:
            for entity in group.entities:
                for text in entity.queries:
                    out.append(
                        Query(
                            text=text,
                            group=group.name,
                            priority=group.priority,
                            search=group.search,
                        )
                    )
        for text in self.field_queries:
            out.append(
                Query(
                    text=text,
                    group=_FIELD_GROUP,
                    priority=_FIELD_PRIORITY,
                    search=SearchSpec(),
                )
            )
        return out

    def tracked_terms(self) -> set[str]:
        """Lowercased names + aliases used to drop off-topic feed items."""
        terms: set[str] = set()
        for group in self.groups:
            for entity in group.entities:
                terms.add(entity.name.lower())
                terms.update(a.lower() for a in entity.aliases)
        floor = defaults.RESEARCH_MIN_TRACKED_TERM_CHARS
        return {t for t in terms if len(t) >= floor}

    def entity_names(self) -> list[str]:
        """Canonical entity names, for the classifier prompt."""
        return sorted({e.name for g in self.groups for e in g.entities})
