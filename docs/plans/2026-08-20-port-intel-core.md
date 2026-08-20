# Research Digest (intel pipeline port) — Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the legacy intel pipeline's collect → classify → synthesize → store → notify core into cosinabox as a generic, config-driven `research_digest` job, fixing the truncation scar with a streamed synthesis call.

**Architecture:** A new `cosinabox/research/` package holds four pure-ish stages behind a `ResearchConfig` loaded from a new user-facing `research.yaml`. Collection fans out Tavily queries and RSS feeds through a thread pool (cosinabox is synchronous end to end — there is no async anywhere in `jobs/` or `tools/`). Synthesis calls Claude through a **new streaming** variant of `call_with_failover`, which removes the fixed `max_tokens` ceiling that truncated two digests. Signals persist to SQLite as the durable record; delivery is a Telegram summary. Publication (GitHub digest, CSV, glossary, curriculum, site index) is explicitly **out of scope** — see "Deferred" below.

**Tech Stack:** Python 3.11+, synchronous `httpx`, `feedparser`, Anthropic SDK streaming, SQLite, `jsonschema`, PyYAML, pytest.

**Spec:** `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md` — the "Missing-feature inventory" row for the intel pipeline and the "Migration note — intel pipeline (2026-08-18)" section. That note is the requirements document for this plan; every scar it records maps to a task below.

**Source being ported:** `~/code/cos-agent/src/intel/{collector,classifier,synthesizer}.py` and `src/scheduler/intel_jobs.py`. Read them for behaviour, **do not copy them** — they are async, and their targets are hardcoded in `config/intel_targets.py` / `config/people_targets.py`.

---

## Global Constraints

Every task's requirements implicitly include these.

- **Synchronous only.** `cosinabox/jobs/` and `cosinabox/tools/` contain zero `async def`. Jobs implement `Job.run(self, context: JobContext) -> str`. Use `concurrent.futures.ThreadPoolExecutor` where the source used `asyncio.gather`.
- **No hardcoded names, orgs, or domains** (CLAUDE.md OSS rule 1). The source hardcodes `rovikrobert`, `cantina-memory-service`, `36kr.com`, specific lab and person names, and region keys `cn_shanghai` / `sg`. All of it becomes `research.yaml` data. Tests use generic fixtures (CLAUDE.md quality rule 4).
- **Defaults live in `defaults.py`** with a comment explaining *why* and the date chosen (CLAUDE.md quality rule 3). No magic numbers in business logic.
- **Optional deps go in an extras group** (CLAUDE.md quality rule 5). This plan adds `research = ["httpx>=0.27", "feedparser>=6.0"]`. *Deviation flagged:* the approved option previewed this as a `tavily` extra; it is named `research` because the same extra also carries the RSS reader, and two extras for one job is noise. Rename it if you disagree — nothing else depends on the name.
- **Graceful degradation** (CLAUDE.md quality rule 6). Missing `research.yaml`, missing `TAVILY_API_KEY`, or an uninstalled extra must make the job report "not configured" and return, never raise.
- **New config file ⇒ new JSON Schema.** `research.yaml` is additive, so no `cosinabox migrate` migration is required (CLAUDE.md safety rule 5 covers *changing* existing schemas). `schema_version: 1`.
- **TDD red-green-commit**, one commit per task, one PR per milestone, `gh pr create ... && gh pr merge --auto --squash` (CLAUDE.md workflow rule 5).
- **Worktree required.** `git worktree add ~/.worktrees/cosinabox/<branch> -b <branch> origin/main` — name `origin/main` explicitly; the local checkout is routinely stale and `CHANGELOG.md` conflicts are the usual symptom.
- **Verification per milestone:** `pytest` (foreground), `ruff check src tests`, `ruff format --check src tests`, `mypy src/cosinabox`. `doctor/checks.py:308` carries a pre-existing `unused-ignore` that only appears on Python 3.14 — ignore it.

## Deferred — do not build here

- **Publication**: `digest_publisher.py` (901 lines — GitHub markdown + CSV, deep-dive generation, glossary, backlog/curriculum splicing, site index). Its own plan. When it lands, carry the scar from cos-agent #187: **never treat a failed read as an empty file** — the publisher appended to `""` and offered the result as a whole-file replacement; only GitHub's `422 "sha wasn't supplied"` prevented data loss.
- **Dead-man's switch** ("has each expected job logged a start in its window?"). The migration note assigns this to cosinabox's scheduler, and it is scheduler-wide rather than research-specific — a 2026-06-15 → 07-20 outage produced four weeks of silence in the legacy system. It deserves its own plan covering every job, not a corner of this one.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/cosinabox/schemas/research.schema.json` | **Create.** JSON Schema for `research.yaml`. |
| `src/cosinabox/schemas/__init__.py` | **Modify.** Add `"research"` to `SCHEMA_NAMES`. |
| `src/cosinabox/cli/validate.py:59-64` | **Modify.** Add `research.yaml` to the `targets` list. |
| `src/cosinabox/templates/user-repo/research.yaml` | **Create.** Generic example config with placeholder tokens. |
| `src/cosinabox/research/__init__.py` | **Create.** Package marker. |
| `src/cosinabox/research/config.py` | **Create.** `ResearchConfig` dataclass + loader + query expansion + tracked-term set. |
| `src/cosinabox/tools/tavily.py` | **Create.** Synchronous Tavily client. |
| `src/cosinabox/research/collector.py` | **Create.** Query fan-out, RSS, URL dedup, tracked-term filter, priority cap. |
| `src/cosinabox/research/classifier.py` | **Create.** Haiku relevance pass, fail-open. |
| `src/cosinabox/agent/failover.py` | **Modify.** Add `call_with_failover_stream`. |
| `src/cosinabox/research/synthesizer.py` | **Create.** Prompt build, streamed call, JSON parse + truncation salvage. |
| `src/cosinabox/research/alerts.py` | **Create.** Zero-signal and near-ceiling health checks. |
| `src/cosinabox/memory/sqlite.py` | **Modify.** `research_signals` + `research_dedup` tables; accessors. |
| `src/cosinabox/jobs/research_digest.py` | **Create.** `ResearchDigestJob(Job)` orchestration. |
| `src/cosinabox/app/jobs.py` | **Modify.** Register `research_digest`. |
| `src/cosinabox/defaults.py` | **Modify.** New `RESEARCH_*` constants. |

---

# Milestone 1 — Config surface

Branch: `feat/research-config`. PR at the end of Task 2.

### Task 1: `research.yaml` schema, template, and validation wiring

**Files:**
- Create: `src/cosinabox/schemas/research.schema.json`
- Create: `src/cosinabox/templates/user-repo/research.yaml`
- Modify: `src/cosinabox/schemas/__init__.py` (`SCHEMA_NAMES`)
- Modify: `src/cosinabox/cli/validate.py` (`targets` list in `validate_cmd`)
- Test: `tests/unit/test_research_schema.py`

**Interfaces:**
- Consumes: `cosinabox.schemas.load_schema` (existing).
- Produces: schema name `"research"`; the `research.yaml` document shape every later task reads.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_schema.py
from __future__ import annotations

import pytest
from jsonschema import ValidationError, validate

from cosinabox.schemas import SCHEMA_NAMES, load_schema

MINIMAL = {
    "schema_version": 1,
    "groups": [
        {
            "name": "example-group",
            "priority": 0,
            "search": {"country": "us", "topic": "news", "time_range": "week"},
            "entities": [
                {"name": "Example Org", "aliases": ["ExOrg"], "queries": ["Example Org launch"]}
            ],
        }
    ],
}


def test_research_is_a_registered_schema():
    assert "research" in SCHEMA_NAMES
    assert load_schema("research")["title"] == "research.yaml"


def test_minimal_config_validates():
    validate(instance=MINIMAL, schema=load_schema("research"))


def test_feeds_and_field_queries_are_optional():
    cfg = {**MINIMAL, "feeds": ["https://example.com/rss"], "field_queries": ["video model"]}
    validate(instance=cfg, schema=load_schema("research"))


def test_group_requires_a_priority():
    bad = {"schema_version": 1, "groups": [{"name": "g", "entities": []}]}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=load_schema("research"))


def test_wrong_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        validate(instance={**MINIMAL, "schema_version": 2}, schema=load_schema("research"))


def test_topic_is_constrained_to_tavily_values():
    bad = {
        "schema_version": 1,
        "groups": [{"name": "g", "priority": 0, "search": {"topic": "sideways"}, "entities": []}],
    }
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=load_schema("research"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_schema.py -v`
Expected: FAIL — `AssertionError` on `SCHEMA_NAMES`, then `FileNotFoundError` for `research.schema.json`.

- [ ] **Step 3: Write the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "research.yaml",
  "type": "object",
  "required": ["schema_version", "groups"],
  "properties": {
    "schema_version": {"const": 1},
    "groups": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "priority", "entities"],
        "properties": {
          "name": {"type": "string", "minLength": 1},
          "priority": {"type": "integer", "minimum": 0},
          "search": {
            "type": "object",
            "properties": {
              "country": {"type": "string", "minLength": 2, "maxLength": 2},
              "topic": {"enum": ["general", "news"]},
              "time_range": {"enum": ["day", "week", "month", "year"]},
              "results_per_query": {"type": "integer", "minimum": 1, "maximum": 20}
            }
          },
          "entities": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["name"],
              "properties": {
                "name": {"type": "string", "minLength": 1},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "queries": {"type": "array", "items": {"type": "string"}}
              }
            }
          }
        }
      }
    },
    "feeds": {"type": "array", "items": {"type": "string"}},
    "field_queries": {"type": "array", "items": {"type": "string"}}
  }
}
```

- [ ] **Step 4: Register the schema and wire validation**

In `src/cosinabox/schemas/__init__.py`:

```python
SCHEMA_NAMES = ("personality", "stakeholders", "jobs", "integrations", "research")
```

In `src/cosinabox/cli/validate.py`, inside `validate_cmd`'s `targets` list, append:

```python
        ("research.yaml", "research", _yaml_loader),
```

`_validate_one` returns `False, "research.yaml MISSING"` when the file is absent, which would fail `cosinabox validate` for every existing user. Guard it — make the research entry optional by skipping a missing file:

```python
    targets: list[tuple[str, str, Callable[[Path], dict[str, Any]]]] = [
        ("personality.md", "personality", _load_personality_frontmatter),
        ("stakeholders.yaml", "stakeholders", _yaml_loader),
        ("jobs.yaml", "jobs", _yaml_loader),
        ("integrations.yaml", "integrations", _yaml_loader),
    ]
    results = [_validate_one(config_dir, *t) for t in targets]
    # research.yaml is opt-in: only the research_digest job reads it, and
    # every repo scaffolded before it existed has none. Validate when present,
    # stay silent when absent — a missing optional file is not an error.
    if (config_dir / "research.yaml").exists():
        results.append(_validate_one(config_dir, "research.yaml", "research", _yaml_loader))
```

- [ ] **Step 5: Write the user-repo template**

`src/cosinabox/templates/user-repo/research.yaml` — placeholder tokens only, matching the `<YOUR_TIMEZONE>` style already used in `jobs.yaml`:

```yaml
# Weekly research digest targets. Read only by the `research_digest` job;
# delete this file if you don't use it.
#
# Each group is a bucket of things you want tracked. `priority` decides who
# survives the result cap when a run collects more than it can synthesize:
# LOWER priority numbers are kept first. Give your few high-value groups a
# low number so a large, noisy group can't crowd them out.
schema_version: 1

groups:
  - name: <YOUR_GROUP_NAME>        # e.g. "frontier-labs"
    priority: 0                     # kept first under the cap
    search:
      country: us                   # 2-letter code passed to the search backend
      topic: news                   # "news" + time_range scopes to fresh articles
      time_range: week
      results_per_query: 5
    entities:
      - name: <ORG_NAME>
        aliases: [<ORG_SHORT_NAME>]           # also used to filter feed noise
        queries: ["<ORG_NAME> product launch"]

  - name: <YOUR_SECOND_GROUP>      # e.g. "people-to-watch"
    priority: 1
    search:
      country: us
      topic: news
      time_range: week
    entities:
      - name: <PERSON_NAME>
        queries: ['"<PERSON_NAME>" <ORG_NAME>']

# Optional RSS/Atom feeds. Feed items are dropped unless their title or
# summary mentions a tracked entity name or alias — without that filter a
# high-volume feed floods the candidate set.
feeds: []

# Optional broad queries with no single owning entity (field-level trends).
field_queries: []
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_schema.py -v`
Expected: PASS (6 tests).

Also run: `pytest tests/ -k validate -v` — the existing validate tests must still pass, proving the optional-file guard didn't break them.

- [ ] **Step 7: Commit**

```bash
git add src/cosinabox/schemas/research.schema.json \
        src/cosinabox/schemas/__init__.py \
        src/cosinabox/cli/validate.py \
        src/cosinabox/templates/user-repo/research.yaml \
        tests/unit/test_research_schema.py
git commit -m "feat(research): research.yaml schema, template, and optional validation"
```

---

### Task 2: `ResearchConfig` loader and query expansion

**Files:**
- Create: `src/cosinabox/research/__init__.py`
- Create: `src/cosinabox/research/config.py`
- Modify: `src/cosinabox/defaults.py`
- Test: `tests/unit/test_research_config.py`

**Interfaces:**
- Consumes: the `research.yaml` shape from Task 1.
- Produces:
  - `@dataclass(frozen=True) SearchSpec(country: str, topic: str, time_range: str | None, results_per_query: int)`
  - `@dataclass(frozen=True) Query(text: str, group: str, priority: int, search: SearchSpec)`
  - `@dataclass(frozen=True) ResearchConfig(groups: tuple[Group, ...], feeds: tuple[str, ...], field_queries: tuple[str, ...])`
  - `ResearchConfig.load(path: Path) -> ResearchConfig | None` — `None` when the file is absent
  - `ResearchConfig.queries() -> list[Query]`
  - `ResearchConfig.tracked_terms() -> set[str]`
  - `ResearchConfig.entity_names() -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_config.py
from __future__ import annotations

import textwrap

from cosinabox.research.config import ResearchConfig

SAMPLE = textwrap.dedent(
    """
    schema_version: 1
    groups:
      - name: labs
        priority: 0
        search:
          country: us
          topic: news
          time_range: week
          results_per_query: 4
        entities:
          - name: Org Alpha
            aliases: [OrgA, "阿尔法"]
            queries: ["Org Alpha launch", "Org Alpha model"]
          - name: Org Beta
            queries: ["Org Beta release"]
      - name: people
        priority: 2
        entities:
          - name: Ada Lovelace
            queries: ['"Ada Lovelace" Org Alpha']
    feeds: ["https://example.com/feed.xml"]
    field_queries: ["video generation benchmark"]
    """
)


def _write(tmp_path, text=SAMPLE):
    p = tmp_path / "research.yaml"
    p.write_text(text)
    return p


def test_missing_file_returns_none(tmp_path):
    assert ResearchConfig.load(tmp_path / "nope.yaml") is None


def test_queries_carry_group_priority_and_search_spec(tmp_path):
    cfg = ResearchConfig.load(_write(tmp_path))
    assert cfg is not None
    labs = [q for q in cfg.queries() if q.group == "labs"]
    assert [q.text for q in labs] == [
        "Org Alpha launch",
        "Org Alpha model",
        "Org Beta release",
    ]
    assert labs[0].priority == 0
    assert labs[0].search.country == "us"
    assert labs[0].search.topic == "news"
    assert labs[0].search.time_range == "week"
    assert labs[0].search.results_per_query == 4


def test_group_without_search_block_gets_defaults(tmp_path):
    cfg = ResearchConfig.load(_write(tmp_path))
    people = [q for q in cfg.queries() if q.group == "people"][0]
    assert people.search.topic == "general"
    assert people.search.time_range is None
    assert people.priority == 2


def test_field_queries_become_lowest_priority_queries(tmp_path):
    cfg = ResearchConfig.load(_write(tmp_path))
    field = [q for q in cfg.queries() if q.group == "field"]
    assert [q.text for q in field] == ["video generation benchmark"]
    # Must sort after every configured group so it can never crowd them out.
    assert field[0].priority > max(q.priority for q in cfg.queries() if q.group != "field")


def test_tracked_terms_include_names_and_aliases_but_drop_short_tokens(tmp_path):
    cfg = ResearchConfig.load(_write(tmp_path))
    terms = cfg.tracked_terms()
    assert "org alpha" in terms
    assert "orga" in terms
    assert "ada lovelace" in terms
    # Two-character CJK aliases are real but too short to match safely.
    assert all(len(t) >= 3 for t in terms)


def test_entity_names_are_deduped_and_sorted(tmp_path):
    cfg = ResearchConfig.load(_write(tmp_path))
    assert cfg.entity_names() == ["Ada Lovelace", "Org Alpha", "Org Beta"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.research'`.

- [ ] **Step 3: Add the defaults**

Append to `src/cosinabox/defaults.py`:

```python
# --- Research digest ---
# Search-backend defaults for a group that omits its own `search:` block.
# "general" + no time window is the safe default: it never silently narrows a
# user's query. Groups that want fresh announcements opt into news+week, which
# is what the legacy tracker needed to stop missing dated releases.
# (2026-08-20 — ported from cos-agent's intel collector.)
RESEARCH_SEARCH_COUNTRY: str = "us"
RESEARCH_SEARCH_TOPIC: str = "general"
RESEARCH_RESULTS_PER_QUERY: int = 5

# Feed items and search results whose title/summary mentions no tracked term
# are dropped. Terms shorter than this match too much ("AI", two-char CJK
# aliases), so they are excluded from the filter set.
# (2026-08-20 — ported; the legacy collector used the same floor.)
RESEARCH_MIN_TRACKED_TERM_CHARS: int = 3
```

- [ ] **Step 4: Write the implementation**

```python
# src/cosinabox/research/__init__.py
"""Config-driven research digest pipeline: collect, classify, synthesize."""
```

```python
# src/cosinabox/research/config.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_config.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit and open the milestone PR**

```bash
git add src/cosinabox/research/ src/cosinabox/defaults.py tests/unit/test_research_config.py
git commit -m "feat(research): ResearchConfig loader, query expansion, tracked terms"
pytest -q && ruff check src tests && ruff format --check src tests && mypy src/cosinabox
git push -u origin feat/research-config
gh pr create --title "feat(research): config surface for the research digest" \
  --body "Milestone 1 of docs/plans/2026-08-20-port-intel-core.md" \
  && gh pr merge --auto --squash
```

---

# Milestone 2 — Collection

Branch: `feat/research-collector`. PR at the end of Task 5.

### Task 3: Synchronous Tavily client

**Files:**
- Create: `src/cosinabox/tools/tavily.py`
- Modify: `pyproject.toml` (add the `research` extra; add it to `dev`)
- Test: `tests/unit/test_tavily_tool.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `TavilyTool(api_key: str)` with
  `search(self, query: str, *, country: str, topic: str, time_range: str | None, max_results: int) -> list[dict[str, Any]]`
  returning dicts shaped `{"title", "url", "snippet", "published", "source"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_tavily_tool.py
from __future__ import annotations

from typing import Any

import pytest

from cosinabox.tools.tavily import TavilyTool

RAW = {
    "results": [
        {
            "title": "Org Alpha ships a thing",
            "url": "https://example.com/a",
            "content": "Body text.",
            "published_date": "2026-08-18",
        },
        {"title": "No url", "content": "x"},
    ]
}


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


def test_search_normalises_results_and_drops_urlless(monkeypatch):
    fake = _FakeClient(_FakeResponse(RAW))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    items = TavilyTool(api_key="k").search(
        "Org Alpha", country="us", topic="news", time_range="week", max_results=4
    )

    assert items == [
        {
            "title": "Org Alpha ships a thing",
            "url": "https://example.com/a",
            "snippet": "Body text.",
            "published": "2026-08-18",
            "source": "example.com",
        }
    ]


def test_news_topic_sends_the_time_window(monkeypatch):
    fake = _FakeClient(_FakeResponse(RAW))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    TavilyTool(api_key="k").search(
        "q", country="us", topic="news", time_range="week", max_results=3
    )

    body = fake.calls[0]["json"]
    assert body["topic"] == "news"
    assert body["time_range"] == "week"
    assert body["max_results"] == 3
    assert body["country"] == "us"


def test_general_topic_omits_time_range(monkeypatch):
    fake = _FakeClient(_FakeResponse(RAW))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    TavilyTool(api_key="k").search(
        "q", country="us", topic="general", time_range=None, max_results=3
    )

    assert "time_range" not in fake.calls[0]["json"]


def test_non_200_raises(monkeypatch):
    fake = _FakeClient(_FakeResponse({"error": "nope"}, status=401))
    monkeypatch.setattr("cosinabox.tools.tavily.httpx.Client", lambda **kw: fake)

    with pytest.raises(RuntimeError, match="Tavily search failed"):
        TavilyTool(api_key="k").search(
            "q", country="us", topic="news", time_range="week", max_results=3
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tavily_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.tools.tavily'`.

- [ ] **Step 3: Add the extra to `pyproject.toml`**

Next to the existing `attio` / `consult` extras:

```toml
# Weekly research digest (research_digest job): Tavily search + RSS reading.
# Optional per CLAUDE.md rule 5 — the engine runs fine without it, the job
# just reports "not configured".
research = ["httpx>=0.27", "feedparser>=6.0"]
```

And in the `dev` group, so CI exercises the research tests — keep in sync with the group above:

```toml
  "httpx>=0.27",
  "feedparser>=6.0",
```

- [ ] **Step 4: Write the implementation**

```python
# src/cosinabox/tools/tavily.py
"""Tavily search tool (optional dep: cosinabox[research]).

Used by the research digest's collector rather than by the chat tool loop.
Tavily is the backend here specifically because it exposes a news topic and a
date window; a general web search over the same queries returns evergreen
product pages, which the synthesizer's recency gate then discards — that
failure starved several tracked entities of signal for months in the legacy
implementation.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except ImportError as e:  # pragma: no cover - exercised by the extras guard
    raise ImportError(
        "cosinabox[research] extra is required. Run: pip install 'cosinabox[research]'"
    ) from e

TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = 20.0


class TavilyTool:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def search(
        self,
        query: str,
        *,
        country: str,
        topic: str,
        time_range: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "query": query,
            "country": country,
            "topic": topic,
            "max_results": max_results,
        }
        # Only meaningful alongside topic="news"; sending it on a general
        # search is silently ignored upstream, so keep the payload honest.
        if time_range:
            body["time_range"] = time_range

        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                TAVILY_URL,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Tavily search failed (HTTP {resp.status_code})")

        out: list[dict[str, Any]] = []
        for item in resp.json().get("results") or []:
            url = item.get("url") or ""
            if not url:
                continue
            out.append(
                {
                    "title": item.get("title") or "",
                    "url": url,
                    "snippet": item.get("content") or "",
                    "published": item.get("published_date") or "",
                    "source": urlparse(url).netloc,
                }
            )
        return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_tavily_tool.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/tools/tavily.py pyproject.toml tests/unit/test_tavily_tool.py
git commit -m "feat(research): synchronous Tavily client behind the [research] extra"
```

---

### Task 4: Collector — fan-out, dedup, tracked-term filter, priority cap

**Files:**
- Create: `src/cosinabox/research/collector.py`
- Modify: `src/cosinabox/defaults.py`
- Test: `tests/unit/test_research_collector.py`

**Interfaces:**
- Consumes: `ResearchConfig`, `Query` (Task 2); `TavilyTool.search` (Task 3).
- Produces:
  - `dedup_by_url(items: list[dict]) -> list[dict]`
  - `filter_by_tracked_terms(items: list[dict], terms: set[str]) -> list[dict]`
  - `cap_by_priority(items: list[dict], *, max_results: int) -> list[dict]`
  - `collect(cfg: ResearchConfig, *, search: SearchBackend, feed_reader: FeedReader | None, max_workers: int) -> CollectionResult`
  - `@dataclass CollectionResult(items: list[dict], search_failed: bool, counts: dict[str, int])`
  - `SearchBackend` protocol matching `TavilyTool.search`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_collector.py
from __future__ import annotations

from typing import Any

from cosinabox.research.collector import (
    cap_by_priority,
    collect,
    dedup_by_url,
    filter_by_tracked_terms,
)
from cosinabox.research.config import Entity, Group, ResearchConfig, SearchSpec


def _cfg() -> ResearchConfig:
    return ResearchConfig(
        groups=(
            Group(
                name="high",
                priority=0,
                search=SearchSpec(topic="news", time_range="week"),
                entities=(Entity(name="Org Alpha", aliases=("OrgA",), queries=("qa",)),),
            ),
            Group(
                name="low",
                priority=5,
                search=SearchSpec(),
                entities=(Entity(name="Org Beta", queries=("qb1", "qb2")),),
            ),
        ),
        feeds=(),
        field_queries=(),
    )


class _FakeSearch:
    """Returns one result per query, tagged so assertions can trace it."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, query: str, *, country: str, topic: str, time_range: str | None, max_results: int
    ) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "topic": topic, "time_range": time_range})
        if query in self.fail_on:
            raise RuntimeError("boom")
        return [{"title": f"t-{query}", "url": f"https://x/{query}", "snippet": "", "source": "x"}]


def test_dedup_keeps_first_occurrence():
    items = [
        {"url": "https://a", "title": "first"},
        {"url": "https://a", "title": "second"},
        {"url": "https://b", "title": "third"},
        {"url": "", "title": "no url"},
    ]
    assert [i["title"] for i in dedup_by_url(items)] == ["first", "third"]


def test_feed_items_without_a_tracked_term_are_dropped():
    items = [
        {"url": "1", "title": "Org Alpha news", "snippet": "", "priority_group": "feed"},
        {"url": "2", "title": "unrelated paper", "snippet": "", "priority_group": "feed"},
        {"url": "3", "title": "unrelated", "snippet": "", "priority_group": "high"},
    ]
    kept = filter_by_tracked_terms(items, {"org alpha"})
    # Feed item 2 is dropped; the non-feed item passes untouched because it
    # came from a targeted query and is relevant by construction.
    assert [i["url"] for i in kept] == ["1", "3"]


def test_cap_keeps_lower_priority_numbers_first():
    items = [{"url": str(n), "priority": 5} for n in range(3)]
    items += [{"url": f"h{n}", "priority": 0} for n in range(3)]
    capped = cap_by_priority(items, max_results=3)
    assert [i["url"] for i in capped] == ["h0", "h1", "h2"]


def test_collect_runs_every_query_with_its_group_search_spec():
    search = _FakeSearch()
    result = collect(_cfg(), search=search, feed_reader=None, max_workers=2)

    assert result.search_failed is False
    assert sorted(c["query"] for c in search.calls) == ["qa", "qb1", "qb2"]
    news = [c for c in search.calls if c["query"] == "qa"][0]
    assert (news["topic"], news["time_range"]) == ("news", "week")
    general = [c for c in search.calls if c["query"] == "qb1"][0]
    assert (general["topic"], general["time_range"]) == ("general", None)
    assert result.counts["raw"] == 3


def test_collect_survives_individual_query_failures():
    search = _FakeSearch(fail_on={"qb1"})
    result = collect(_cfg(), search=search, feed_reader=None, max_workers=2)
    # One query died; the other two still produced results.
    assert result.search_failed is False
    assert result.counts["raw"] == 2


def test_collect_reports_total_search_failure():
    search = _FakeSearch(fail_on={"qa", "qb1", "qb2"})
    result = collect(_cfg(), search=search, feed_reader=None, max_workers=2)
    assert result.search_failed is True
    assert result.items == []


def test_feed_failure_does_not_abort_collection():
    def _bad_reader(feeds: tuple[str, ...]) -> list[dict[str, Any]]:
        raise RuntimeError("feed down")

    search = _FakeSearch()
    result = collect(_cfg(), search=search, feed_reader=_bad_reader, max_workers=2)
    assert result.search_failed is False
    assert result.counts["raw"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.research.collector'`.

- [ ] **Step 3: Add the defaults**

Append to the research block in `src/cosinabox/defaults.py`:

```python
# Hard cap on candidates handed to synthesis. Sized for the synthesis prompt's
# token budget, not for completeness — beyond this, extra candidates cost
# tokens without changing the digest. Items are dropped lowest-priority-first
# so a large noisy group cannot displace a targeted one.
# (2026-08-20 — ported; the legacy cap silently sliced off an entire region's
# results for eleven weeks because it capped in append order instead.)
RESEARCH_MAX_CANDIDATES: int = 120

# Concurrent search requests. The backend rate-limits, and the legacy
# implementation ran queries strictly sequentially for that reason; a small
# pool is a measured relaxation, not a free-for-all.
# (2026-08-20)
RESEARCH_MAX_WORKERS: int = 4

# Feed items older than this are ignored — the digest is weekly, so a month-old
# post is not news. (2026-08-20 — ported.)
RESEARCH_FEED_MAX_AGE_DAYS: int = 7
```

- [ ] **Step 4: Write the implementation**

```python
# src/cosinabox/research/collector.py
"""Stage 1: gather candidate items from search and feeds.

Runs outside any model call — this is a plain data pipeline whose output
becomes the synthesis prompt.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from cosinabox import defaults
from cosinabox.research.config import Query, ResearchConfig

logger = logging.getLogger(__name__)

# Items from feeds are untargeted, so they must earn their place by mentioning
# a tracked term. Items from queries are relevant by construction.
FEED_GROUP = "feed"
_FEED_PRIORITY = 20_000


class SearchBackend(Protocol):
    def __call__(
        self,
        query: str,
        *,
        country: str,
        topic: str,
        time_range: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]: ...


class FeedReader(Protocol):
    def __call__(self, feeds: tuple[str, ...]) -> list[dict[str, Any]]: ...


@dataclass
class CollectionResult:
    items: list[dict[str, Any]]
    search_failed: bool
    counts: dict[str, int] = field(default_factory=dict)


def dedup_by_url(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop repeat URLs, keeping the first occurrence. Urlless items are noise."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def filter_by_tracked_terms(
    items: list[dict[str, Any]], terms: set[str]
) -> list[dict[str, Any]]:
    """Keep feed items only when they mention a tracked term.

    Everything else passes through: it arrived via a targeted query. A single
    high-volume feed otherwise floods the candidate set and displaces the
    results the user actually asked for.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("priority_group") != FEED_GROUP:
            out.append(item)
            continue
        haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if any(term in haystack for term in terms):
            out.append(item)
    return out


def cap_by_priority(
    items: list[dict[str, Any]], *, max_results: int
) -> list[dict[str, Any]]:
    """Trim to `max_results`, dropping the highest priority numbers first.

    Sorting before slicing is the whole point: slicing in append order is what
    let one group's results be cut entirely in the legacy implementation.
    Python's sort is stable, so order within a priority level is preserved.
    """
    ordered = sorted(items, key=lambda i: i.get("priority", _FEED_PRIORITY))
    return ordered[:max_results]


def _run_query(search: SearchBackend, q: Query) -> list[dict[str, Any]]:
    items = search(
        q.text,
        country=q.search.country,
        topic=q.search.topic,
        time_range=q.search.time_range,
        max_results=q.search.results_per_query,
    )
    for item in items:
        item["priority"] = q.priority
        item["priority_group"] = q.group
    return items


def collect(
    cfg: ResearchConfig,
    *,
    search: SearchBackend,
    feed_reader: FeedReader | None,
    max_workers: int = defaults.RESEARCH_MAX_WORKERS,
) -> CollectionResult:
    """Run every configured query plus the feeds, then dedup, filter and cap.

    A single failing query is logged and skipped. Only *every* query failing
    counts as `search_failed` — synthesizing from feeds alone would produce a
    digest that looks fine and silently omits the tracked entities.
    """
    queries = cfg.queries()
    raw: list[dict[str, Any]] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_query, search, q): q for q in queries}
        for future, q in futures.items():
            try:
                raw.extend(future.result())
            except Exception as exc:
                failures += 1
                logger.warning("Research query %r failed: %s", q.text, exc)

    search_failed = bool(queries) and failures == len(queries)
    if search_failed:
        logger.error(
            "Aborting collection: all %d search queries failed", len(queries)
        )
        return CollectionResult(items=[], search_failed=True, counts={"raw": 0})

    if feed_reader and cfg.feeds:
        try:
            for item in feed_reader(cfg.feeds):
                item["priority"] = _FEED_PRIORITY
                item["priority_group"] = FEED_GROUP
                raw.append(item)
        except Exception as exc:
            # Feeds are supplementary; losing them degrades the digest but
            # does not invalidate it.
            logger.warning("Feed collection failed: %s", exc)

    deduped = dedup_by_url(raw)
    filtered = filter_by_tracked_terms(deduped, cfg.tracked_terms())
    capped = cap_by_priority(filtered, max_results=defaults.RESEARCH_MAX_CANDIDATES)

    counts = {
        "raw": len(raw),
        "deduped": len(deduped),
        "filtered": len(filtered),
        "capped": len(capped),
    }
    logger.info(
        "Research collection: %d raw -> %d deduped -> %d filtered -> %d capped",
        counts["raw"], counts["deduped"], counts["filtered"], counts["capped"],
    )
    return CollectionResult(items=capped, search_failed=False, counts=counts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_collector.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/research/collector.py src/cosinabox/defaults.py \
        tests/unit/test_research_collector.py
git commit -m "feat(research): collector with URL dedup, term filter, priority cap"
```

---

### Task 5: RSS feed reader

**Files:**
- Create: `src/cosinabox/research/feeds.py`
- Test: `tests/unit/test_research_feeds.py`

**Interfaces:**
- Consumes: `defaults.RESEARCH_FEED_MAX_AGE_DAYS`.
- Produces: `read_feeds(feeds: tuple[str, ...], *, now: datetime, max_age_days: int) -> list[dict]` — satisfies the `FeedReader` protocol from Task 4 when partially applied.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_feeds.py
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from cosinabox.research.feeds import read_feeds

NOW = datetime(2026, 8, 20, tzinfo=UTC)


def _entry(title: str, link: str, *, day: int) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        link=link,
        summary=f"summary of {title}",
        published_parsed=(2026, 8, day, 0, 0, 0, 0, 0, 0),
    )


def test_recent_entries_are_returned_with_normalised_keys(monkeypatch):
    monkeypatch.setattr(
        "cosinabox.research.feeds.feedparser.parse",
        lambda url: SimpleNamespace(entries=[_entry("Fresh", "https://x/1", day=18)]),
    )
    items = read_feeds(("https://f",), now=NOW, max_age_days=7)
    assert items == [
        {
            "title": "Fresh",
            "url": "https://x/1",
            "snippet": "summary of Fresh",
            "published": "2026-08-18",
            "source": "x",
        }
    ]


def test_entries_older_than_the_window_are_dropped(monkeypatch):
    monkeypatch.setattr(
        "cosinabox.research.feeds.feedparser.parse",
        lambda url: SimpleNamespace(entries=[_entry("Stale", "https://x/2", day=1)]),
    )
    assert read_feeds(("https://f",), now=NOW, max_age_days=7) == []


def test_one_bad_feed_does_not_lose_the_others(monkeypatch):
    def _parse(url: str):
        if "bad" in url:
            raise RuntimeError("unreachable")
        return SimpleNamespace(entries=[_entry("Good", "https://x/3", day=19)])

    monkeypatch.setattr("cosinabox.research.feeds.feedparser.parse", _parse)
    items = read_feeds(("https://bad", "https://good"), now=NOW, max_age_days=7)
    assert [i["title"] for i in items] == ["Good"]


def test_entry_without_a_date_is_kept(monkeypatch):
    entry = SimpleNamespace(
        title="Undated", link="https://x/4", summary="s", published_parsed=None
    )
    monkeypatch.setattr(
        "cosinabox.research.feeds.feedparser.parse",
        lambda url: SimpleNamespace(entries=[entry]),
    )
    items = read_feeds(("https://f",), now=NOW, max_age_days=7)
    # No date means we cannot prove it is stale; the tracked-term filter and
    # the priority cap are the downstream guards.
    assert [i["title"] for i in items] == ["Undated"]
    assert items[0]["published"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_feeds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.research.feeds'`.

- [ ] **Step 3: Write the implementation**

```python
# src/cosinabox/research/feeds.py
"""RSS/Atom reading for the research digest (optional dep: cosinabox[research])."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

try:
    import feedparser
except ImportError as e:  # pragma: no cover - exercised by the extras guard
    raise ImportError(
        "cosinabox[research] extra is required. Run: pip install 'cosinabox[research]'"
    ) from e

from cosinabox import defaults

logger = logging.getLogger(__name__)


def read_feeds(
    feeds: tuple[str, ...],
    *,
    now: datetime | None = None,
    max_age_days: int = defaults.RESEARCH_FEED_MAX_AGE_DAYS,
) -> list[dict[str, Any]]:
    """Fetch each feed and return entries published within the window.

    One unreachable feed must not cost the others, so failures are logged per
    feed. Entries with no parseable date are kept: we cannot prove they are
    stale, and the tracked-term filter plus the priority cap downstream keep
    them from dominating.
    """
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=max_age_days)).date()
    out: list[dict[str, Any]] = []

    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("Feed %s failed: %s", url, exc)
            continue

        for entry in getattr(parsed, "entries", []) or []:
            published = ""
            stamp = getattr(entry, "published_parsed", None)
            if stamp:
                try:
                    entry_date = datetime(*stamp[:6], tzinfo=UTC).date()
                except (TypeError, ValueError):
                    entry_date = None
                else:
                    if entry_date < cutoff:
                        continue
                    published = entry_date.isoformat()

            link = getattr(entry, "link", "") or ""
            if not link:
                continue
            out.append(
                {
                    "title": getattr(entry, "title", "") or "",
                    "url": link,
                    "snippet": getattr(entry, "summary", "") or "",
                    "published": published,
                    "source": urlparse(link).netloc,
                }
            )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_feeds.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit and open the milestone PR**

```bash
git add src/cosinabox/research/feeds.py tests/unit/test_research_feeds.py
git commit -m "feat(research): RSS reader with per-feed failure isolation"
pytest -q && ruff check src tests && ruff format --check src tests && mypy src/cosinabox
git push -u origin feat/research-collector
gh pr create --title "feat(research): collection stage" \
  --body "Milestone 2 of docs/plans/2026-08-20-port-intel-core.md" \
  && gh pr merge --auto --squash
```

---

# Milestone 3 — Classification

Branch: `feat/research-classifier`. PR at the end of Task 6.

### Task 6: Haiku relevance pass (fail-open)

**Files:**
- Create: `src/cosinabox/research/classifier.py`
- Modify: `src/cosinabox/defaults.py`
- Test: `tests/unit/test_research_classifier.py`

**Interfaces:**
- Consumes: collector output (`list[dict]` with `title`/`url`/`snippet`); `ResearchConfig.entity_names()`.
- Produces: `classify(items: list[dict], *, entity_names: list[str], client: Any) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_classifier.py
from __future__ import annotations

from types import SimpleNamespace

from cosinabox.research.classifier import classify

ITEMS = [
    {"title": "Org Alpha ships", "url": "https://x/1", "snippet": ""},
    {"title": "Unrelated paper", "url": "https://x/2", "snippet": ""},
    {"title": "Org Beta hires", "url": "https://x/3", "snippet": ""},
]


def _client(text: str):
    """Minimal stand-in for the Anthropic client's messages.create."""
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
    return SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: response)
    )


def test_keeps_only_indices_the_model_marked_relevant():
    kept = classify(ITEMS, entity_names=["Org Alpha", "Org Beta"], client=_client("[0, 2]"))
    assert [i["url"] for i in kept] == ["https://x/1", "https://x/3"]


def test_tolerates_json_wrapped_in_prose():
    kept = classify(
        ITEMS,
        entity_names=["Org Alpha"],
        client=_client("Here you go:\n```json\n[1]\n```"),
    )
    assert [i["url"] for i in kept] == ["https://x/2"]


def test_out_of_range_indices_are_ignored():
    kept = classify(ITEMS, entity_names=["Org Alpha"], client=_client("[0, 99, -1]"))
    assert [i["url"] for i in kept] == ["https://x/1"]


def test_unparseable_response_fails_open():
    kept = classify(ITEMS, entity_names=["Org Alpha"], client=_client("no idea"))
    # Fail open: synthesis is prompted never to fabricate, so an over-broad
    # candidate set is far cheaper than silently dropping every signal.
    assert kept == ITEMS


def test_api_error_fails_open():
    def _boom(**kw):
        raise RuntimeError("429")

    client = SimpleNamespace(messages=SimpleNamespace(create=_boom))
    assert classify(ITEMS, entity_names=["Org Alpha"], client=client) == ITEMS


def test_empty_input_short_circuits_without_calling_the_model():
    calls: list[object] = []

    def _record(**kw):
        calls.append(kw)
        raise AssertionError("should not be called")

    client = SimpleNamespace(messages=SimpleNamespace(create=_record))
    assert classify([], entity_names=["Org Alpha"], client=client) == []
    assert calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.research.classifier'`.

- [ ] **Step 3: Add the default**

```python
# The relevance pre-pass runs on the cheapest model: it answers one narrow
# question ("is this item about a tracked entity?") thousands of times, and
# using the synthesis model for it costs roughly 20x for no gain.
# (2026-08-20 — ported from cos-agent's intel classifier.)
RESEARCH_CLASSIFIER_MODEL: str = "claude-haiku-4-5-20251001"
RESEARCH_CLASSIFIER_MAX_TOKENS: int = 2048
```

- [ ] **Step 4: Write the implementation**

```python
# src/cosinabox/research/classifier.py
"""Cheap relevance pass between collection and synthesis.

The keyword filter in the collector is deliberately blunt — it matches a
tracked term anywhere in the title or summary, which lets through papers that
name-drop an entity in an unrelated citation. This pass asks the cheapest
model to make that judgement properly.

Fails open by design. Synthesis is prompted never to fabricate, so handing it
a few irrelevant candidates costs tokens; dropping every candidate because the
classifier had a bad minute costs the entire digest.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cosinabox import defaults

logger = logging.getLogger(__name__)

_PROMPT = """You are filtering candidate news items for a research digest.

Tracked entities:
{entities}

Below are numbered candidate items. Return a JSON array of the indices whose
item is genuinely *about* one or more tracked entities — an announcement,
release, hire, funding round, policy change or result involving them.

Exclude items that merely mention an entity in passing (a citation, a
comparison table, an unrelated related-work section).

Return ONLY the JSON array, e.g. [0, 3, 7].

Items:
{items}
"""


def _extract_indices(text: str) -> list[int] | None:
    """Pull a JSON array of ints out of the response, tolerating prose."""
    for candidate in (text.strip(), *_fenced_blocks(text), *_bare_arrays(text)):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list) and all(isinstance(i, int) for i in parsed):
            return parsed
    return None


def _fenced_blocks(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)]


def _bare_arrays(text: str) -> list[str]:
    match = re.search(r"\[[\s\d,\-]*\]", text)
    return [match.group()] if match else []


def _response_text(response: Any) -> str:
    return "".join(
        block.text for block in getattr(response, "content", []) if getattr(block, "type", "") == "text"
    )


def classify(
    items: list[dict[str, Any]], *, entity_names: list[str], client: Any
) -> list[dict[str, Any]]:
    """Return the subset of `items` the model judged relevant.

    Returns `items` unchanged on any failure — see the module docstring.
    """
    if not items:
        return []

    listing = "\n".join(
        f"{n}. {i.get('title', '')} — {i.get('snippet', '')[:200]}"
        for n, i in enumerate(items)
    )
    prompt = _PROMPT.format(
        entities="\n".join(f"- {name}" for name in entity_names),
        items=listing,
    )

    try:
        response = client.messages.create(
            model=defaults.RESEARCH_CLASSIFIER_MODEL,
            max_tokens=defaults.RESEARCH_CLASSIFIER_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Research classifier unavailable (%s) — keeping all candidates", exc)
        return items

    indices = _extract_indices(_response_text(response))
    if indices is None:
        logger.warning("Research classifier returned no parseable indices — keeping all candidates")
        return items

    kept = [items[i] for i in indices if 0 <= i < len(items)]
    logger.info("Research classifier kept %d of %d candidates", len(kept), len(items))
    return kept
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_classifier.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit and open the milestone PR**

```bash
git add src/cosinabox/research/classifier.py src/cosinabox/defaults.py \
        tests/unit/test_research_classifier.py
git commit -m "feat(research): fail-open Haiku relevance classifier"
pytest -q && ruff check src tests && ruff format --check src tests && mypy src/cosinabox
git push -u origin feat/research-classifier
gh pr create --title "feat(research): relevance classifier" \
  --body "Milestone 3 of docs/plans/2026-08-20-port-intel-core.md" \
  && gh pr merge --auto --squash
```

---

# Milestone 4 — Synthesis (the truncation fix)

Branch: `feat/research-synthesis`. PR at the end of Task 9.

**Why this milestone exists.** The legacy stage-2 call is non-streaming with `max_tokens=16000`. Two digests (2026-08-03, 2026-08-17) were cut off at 56,002 and 57,795 characters against that ceiling, and the second went unnoticed for two weeks because nothing alerted. Streaming removes the practical ceiling; Task 9 adds the alert that should have caught it.

### Task 7: `call_with_failover_stream`

**Files:**
- Modify: `src/cosinabox/agent/failover.py`
- Test: `tests/unit/test_failover_stream.py`

**Interfaces:**
- Consumes: `MODEL_FAILOVER_CHAIN` (existing), the existing `call_with_failover` chain-walking logic.
- Produces: `call_with_failover_stream(client, model, *, system, messages, max_tokens, tools=None) -> tuple[str, str]` returning `(accumulated_text, model_actually_used)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_failover_stream.py
from __future__ import annotations

from types import SimpleNamespace

import anthropic
import pytest

from cosinabox.agent.failover import call_with_failover_stream
from cosinabox.defaults import MODEL_FAILOVER_CHAIN


class _FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def text_stream(self):
        yield from self._chunks


def _client(behaviour):
    return SimpleNamespace(messages=SimpleNamespace(stream=behaviour))


def test_accumulates_the_streamed_text():
    client = _client(lambda **kw: _FakeStream(["Hello, ", "world", "!"]))
    text, model = call_with_failover_stream(
        client, MODEL_FAILOVER_CHAIN[0], system="s", messages=[], max_tokens=64_000
    )
    assert text == "Hello, world!"
    assert model == MODEL_FAILOVER_CHAIN[0]


def test_passes_max_tokens_and_system_through():
    seen: dict[str, object] = {}

    def _stream(**kw):
        seen.update(kw)
        return _FakeStream(["x"])

    call_with_failover_stream(
        _client(_stream),
        MODEL_FAILOVER_CHAIN[0],
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64_000,
    )
    assert seen["max_tokens"] == 64_000
    assert seen["system"] == "sys"
    assert seen["messages"] == [{"role": "user", "content": "hi"}]


def test_falls_through_the_chain_on_overload():
    attempts: list[str] = []

    def _stream(**kw):
        attempts.append(kw["model"])
        if len(attempts) == 1:
            raise anthropic.APIStatusError(
                "overloaded", response=SimpleNamespace(status_code=529), body=None
            )
        return _FakeStream(["ok"])

    text, model = call_with_failover_stream(
        _client(_stream), MODEL_FAILOVER_CHAIN[0], system="s", messages=[], max_tokens=1000
    )
    assert text == "ok"
    assert attempts == list(MODEL_FAILOVER_CHAIN[:2])
    assert model == MODEL_FAILOVER_CHAIN[1]


def test_raises_after_the_chain_is_exhausted():
    def _stream(**kw):
        raise anthropic.APIStatusError(
            "overloaded", response=SimpleNamespace(status_code=529), body=None
        )

    with pytest.raises(anthropic.APIError):
        call_with_failover_stream(
            _client(_stream), MODEL_FAILOVER_CHAIN[0], system="s", messages=[], max_tokens=1000
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_failover_stream.py -v`
Expected: FAIL — `ImportError: cannot import name 'call_with_failover_stream'`.

- [ ] **Step 3: Write the implementation**

Append to `src/cosinabox/agent/failover.py`:

```python
def call_with_failover_stream(
    client: Any,
    model: str,
    *,
    system: Any,
    messages: list[dict[str, Any]],
    max_tokens: int,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Streamed sibling of `call_with_failover`, returning accumulated text.

    Streaming exists here for one reason: a non-streamed call must declare a
    `max_tokens` it will not exceed, and a long structured response silently
    truncates against it. Streaming lets the ceiling be set generously without
    risking a mid-object cut, which is what corrupted two weekly digests in the
    legacy implementation.

    Returns `(text, model_actually_used)` so the caller can attribute cost.
    Raises `anthropic.APIError` once the whole chain is exhausted.
    """
    try:
        start_idx = MODEL_FAILOVER_CHAIN.index(model)
        chain: tuple[str, ...] = MODEL_FAILOVER_CHAIN[start_idx:]
    except ValueError:
        chain = (model,)

    last_error: Exception | None = None
    for candidate in chain:
        kwargs: dict[str, Any] = {
            "model": candidate,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            chunks: list[str] = []
            with client.messages.stream(**kwargs) as stream:
                for chunk in stream.text_stream:
                    chunks.append(chunk)
            return "".join(chunks), candidate
        except anthropic.APIError as exc:
            last_error = exc
            status = getattr(exc, "status_code", None)
            message = str(exc)
            retryable = status in (429, 529) or "overloaded" in message.lower()
            if not retryable:
                raise
            logger.warning(
                "Streamed call to %s failed (%s) — trying next in chain", candidate, status
            )

    assert last_error is not None
    raise last_error
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_failover_stream.py -v`
Expected: PASS (4 tests).

Also run: `pytest tests/ -k failover -v` — the existing non-streaming tests must be untouched.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/agent/failover.py tests/unit/test_failover_stream.py
git commit -m "feat(agent): streaming call_with_failover variant"
```

---

### Task 8: Synthesizer — prompt, streamed call, parse with salvage

**Files:**
- Create: `src/cosinabox/research/synthesizer.py`
- Modify: `src/cosinabox/defaults.py`
- Test: `tests/unit/test_research_synthesizer.py`

**Interfaces:**
- Consumes: `call_with_failover_stream` (Task 7); collector items; `ResearchConfig`.
- Produces:
  - `SYNTHESIS_FAILED_NOTICE: str`
  - `format_candidates(items: list[dict]) -> str`
  - `build_prompt(cfg, *, candidates: str, dedup_index: list[dict], week_of: str) -> str`
  - `parse_response(text: str) -> dict` with keys `telegram_summary`, `full_report`, `signal_records`, `follow_up_signals`
  - `synthesize(cfg, *, items, dedup_index, week_of, client, model) -> tuple[dict, str]` returning `(parsed, raw_text)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_synthesizer.py
from __future__ import annotations

import json
from types import SimpleNamespace

from cosinabox.research.config import Entity, Group, ResearchConfig, SearchSpec
from cosinabox.research.synthesizer import (
    SYNTHESIS_FAILED_NOTICE,
    build_prompt,
    format_candidates,
    parse_response,
    synthesize,
)

CFG = ResearchConfig(
    groups=(
        Group(
            name="labs",
            priority=0,
            search=SearchSpec(),
            entities=(Entity(name="Org Alpha", aliases=("OrgA",)),),
        ),
    ),
    feeds=(),
    field_queries=(),
)

GOOD = {
    "telegram_summary": "One thing happened.",
    "full_report": "# Report\n\nDetail.",
    "signal_records": [{"headline": "H", "source_url": "https://x/1"}],
    "follow_up_signals": ["dig into H"],
}


def test_format_candidates_includes_source_date_title_and_url():
    text = format_candidates(
        [{"source": "x.com", "published": "2026-08-18", "title": "T", "snippet": "S", "url": "https://x/1"}]
    )
    assert "[x.com]" in text and "(2026-08-18)" in text and "T" in text and "https://x/1" in text


def test_format_candidates_handles_an_empty_set():
    assert "No candidates" in format_candidates([])


def test_prompt_lists_tracked_entities_and_the_dedup_index():
    prompt = build_prompt(
        CFG,
        candidates="CAND",
        dedup_index=[{"headline": "Old news", "url": "https://x/0"}],
        week_of="2026-08-17",
    )
    assert "Org Alpha" in prompt
    assert "OrgA" in prompt
    assert "Old news" in prompt
    assert "2026-08-17" in prompt
    assert "CAND" in prompt


def test_prompt_says_first_run_when_the_index_is_empty():
    assert "first run" in build_prompt(CFG, candidates="C", dedup_index=[], week_of="w").lower()


def test_parse_accepts_clean_json():
    assert parse_response(json.dumps(GOOD)) == GOOD


def test_parse_accepts_fenced_json():
    parsed = parse_response(f"Sure:\n```json\n{json.dumps(GOOD)}\n```")
    assert parsed["telegram_summary"] == "One thing happened."


def test_parse_salvages_a_truncated_object():
    truncated = json.dumps(GOOD)[: json.dumps(GOOD).index('"signal_records"')] + '"signal_records": [{"headline": "H"'
    parsed = parse_response(truncated)
    # The fields that finished before the cut must survive.
    assert parsed["telegram_summary"] == "One thing happened."
    assert parsed["full_report"] == "# Report\n\nDetail."


def test_parse_fills_missing_keys():
    parsed = parse_response(json.dumps({"telegram_summary": "s"}))
    assert parsed["full_report"] == ""
    assert parsed["signal_records"] == []
    assert parsed["follow_up_signals"] == []


def test_parse_returns_the_failure_notice_on_garbage():
    parsed = parse_response("I could not comply.")
    assert parsed["telegram_summary"] == SYNTHESIS_FAILED_NOTICE
    assert parsed["signal_records"] == []


def test_synthesize_streams_and_returns_raw_text(monkeypatch):
    seen: dict[str, object] = {}

    def _fake_stream(client, model, *, system, messages, max_tokens, tools=None):
        seen.update({"model": model, "max_tokens": max_tokens, "tools": tools})
        return json.dumps(GOOD), model

    monkeypatch.setattr(
        "cosinabox.research.synthesizer.call_with_failover_stream", _fake_stream
    )
    parsed, raw = synthesize(
        CFG,
        items=[{"title": "T", "url": "https://x/1"}],
        dedup_index=[],
        week_of="2026-08-17",
        client=SimpleNamespace(),
        model="claude-sonnet-5",
    )
    assert parsed["telegram_summary"] == "One thing happened."
    assert json.loads(raw) == GOOD
    # No tools: this is pure synthesis over pre-fetched data.
    assert seen["tools"] is None
    assert seen["max_tokens"] >= 32_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_synthesizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.research.synthesizer'`.

- [ ] **Step 3: Add the default**

```python
# Streamed synthesis ceiling. Generous on purpose: the call streams, so a high
# ceiling costs nothing unless the model actually uses it, whereas a low one
# silently truncates a long structured response mid-object.
# (2026-08-20 — the legacy non-streaming call capped at 16000 and cut two
# weekly digests off at ~56k characters.)
RESEARCH_SYNTHESIS_MAX_TOKENS: int = 32_000

# Warn when output reaches this share of the ceiling. Legacy output crept
# 33k -> 49k chars over four weeks before the first truncation; a warning at
# 80% turns the next one into a heads-up instead of a lost digest.
RESEARCH_SYNTHESIS_WARN_RATIO: float = 0.8

# Observed characters per output token for this JSON shape, used to convert the
# token ceiling into the character budget the alert compares against.
RESEARCH_SYNTHESIS_CHARS_PER_TOKEN: float = 3.6
```

- [ ] **Step 4: Write the implementation**

```python
# src/cosinabox/research/synthesizer.py
"""Stage 2: turn candidate items into a digest via one streamed model call."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cosinabox import defaults
from cosinabox.agent.failover import call_with_failover_stream
from cosinabox.research.config import ResearchConfig

logger = logging.getLogger(__name__)

# Callers match on this to tell a failed run from a genuinely quiet week.
# Don't reword it in one place only.
SYNTHESIS_FAILED_NOTICE = "Research digest: synthesis failed — check logs."

_REQUIRED_KEYS = ("telegram_summary", "full_report", "signal_records", "follow_up_signals")

_PROMPT = """You are compiling a weekly research digest for the week of {week_of}.

Tracked entities:
{entities}

Already reported in recent weeks — do NOT repeat these:
{dedup_index}

Candidate items collected this week:
{candidates}

Return ONLY a JSON object with exactly these keys:
- "telegram_summary": a short plain-text summary, at most 1200 characters.
- "full_report": a markdown report.
- "signal_records": a list of objects, each with "headline", "source_url",
  "entity", and "why_it_matters".
- "follow_up_signals": a list of short strings naming things worth a deeper look.

Rules:
- Use ONLY the candidate items above. Never invent a fact, a date, or a URL.
- If nothing meaningful happened, say so plainly and return an empty
  "signal_records" list. A quiet week is a valid outcome.
"""


def format_candidates(items: list[dict[str, Any]]) -> str:
    """Render collected items as the prompt's data block."""
    if not items:
        return "No candidates were collected this week."
    blocks = []
    for item in items:
        date = f" ({item.get('published')})" if item.get("published") else ""
        blocks.append(
            f"[{item.get('source', 'unknown')}]{date} {item.get('title', '')}\n"
            f"{item.get('snippet', '')}\n{item.get('url', '')}"
        )
    return "\n\n".join(blocks)


def build_prompt(
    cfg: ResearchConfig,
    *,
    candidates: str,
    dedup_index: list[dict[str, Any]],
    week_of: str,
) -> str:
    entities = "\n".join(
        f"- {e.name}" + (f" (aliases: {', '.join(e.aliases)})" if e.aliases else "")
        for g in cfg.groups
        for e in g.entities
    )
    if dedup_index:
        index = "\n".join(
            f"- {i.get('headline', '')} ({i.get('url', '')})" for i in dedup_index
        )
    else:
        index = "(Nothing yet — this is the first run.)"
    return _PROMPT.format(
        week_of=week_of, entities=entities, dedup_index=index, candidates=candidates
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    for candidate in (
        text.strip(),
        *[m.group(1).strip() for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)],
        *([m.group()] if (m := re.search(r"\{[\s\S]*\}", text)) else []),
    ):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _salvage_truncated(text: str) -> dict[str, Any] | None:
    """Recover the fields of a JSON object that was cut off mid-write.

    A response cut short still carries every field it finished — the summary,
    the report, some signals — and a strict parse throws all of it away. Walk
    the text tracking string/escape state, find the last point where a
    top-level pair completed, and close the object there.
    """
    start = text.find("{")
    if start == -1:
        return None

    stack: list[str] = []
    in_string = False
    escaped = False
    last_safe: int | None = None

    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
        elif in_string:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if len(stack) == 1:  # closed a value directly under the root
                last_safe = i + 1
        elif ch == "," and len(stack) == 1:
            last_safe = i

    if last_safe is None:
        return None
    try:
        result: dict[str, Any] = json.loads(text[start:last_safe].rstrip(", ") + "}")
    except json.JSONDecodeError:
        return None
    return result


def parse_response(text: str) -> dict[str, Any]:
    """Parse the synthesis JSON, salvaging a truncated object before giving up."""
    parsed = _extract_json(text)
    if not parsed:
        parsed = _salvage_truncated(text)
        if parsed:
            logger.warning("Synthesis response was truncated; salvaged: %s", sorted(parsed))

    if not parsed:
        logger.error("Could not parse synthesis response: %s", text[:200])
        return {
            "telegram_summary": SYNTHESIS_FAILED_NOTICE,
            "full_report": f"Raw response:\n{text}",
            "signal_records": [],
            "follow_up_signals": [],
        }

    for key in _REQUIRED_KEYS:
        if key not in parsed:
            parsed[key] = [] if key in ("signal_records", "follow_up_signals") else ""
    return parsed


def synthesize(
    cfg: ResearchConfig,
    *,
    items: list[dict[str, Any]],
    dedup_index: list[dict[str, Any]],
    week_of: str,
    client: Any,
    model: str,
) -> tuple[dict[str, Any], str]:
    """Run stage 2 and return `(parsed, raw_text)`.

    `raw_text` is returned so the caller can size the output against the
    ceiling — see `research.alerts.synthesis_alerts`.
    """
    prompt = build_prompt(
        cfg,
        candidates=format_candidates(items),
        dedup_index=dedup_index,
        week_of=week_of,
    )
    raw, used_model = call_with_failover_stream(
        client,
        model,
        system=None,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=defaults.RESEARCH_SYNTHESIS_MAX_TOKENS,
        tools=None,
    )
    logger.info("Synthesis completed on %s (%d chars)", used_model, len(raw))
    return parse_response(raw), raw
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_synthesizer.py -v`
Expected: PASS (10 tests).

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/research/synthesizer.py src/cosinabox/defaults.py \
        tests/unit/test_research_synthesizer.py
git commit -m "feat(research): streamed synthesis with truncation salvage"
```

---

### Task 9: Health alerts — zero-signal and near-ceiling

**Files:**
- Create: `src/cosinabox/research/alerts.py`
- Test: `tests/unit/test_research_alerts.py`

**Interfaces:**
- Consumes: `SYNTHESIS_FAILED_NOTICE` (Task 8); the `RESEARCH_SYNTHESIS_*` defaults.
- Produces: `synthesis_alerts(*, telegram_summary: str, signal_count: int, raw_length: int) -> list[str]` — empty list means healthy.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_alerts.py
from __future__ import annotations

from cosinabox import defaults
from cosinabox.research.alerts import synthesis_alerts
from cosinabox.research.synthesizer import SYNTHESIS_FAILED_NOTICE

BUDGET = defaults.RESEARCH_SYNTHESIS_MAX_TOKENS * defaults.RESEARCH_SYNTHESIS_CHARS_PER_TOKEN


def test_healthy_run_produces_no_alerts():
    assert synthesis_alerts(telegram_summary="Real summary.", signal_count=4, raw_length=1000) == []


def test_failure_notice_alerts():
    alerts = synthesis_alerts(
        telegram_summary=SYNTHESIS_FAILED_NOTICE, signal_count=0, raw_length=42
    )
    assert len(alerts) == 1
    assert "no parseable output" in alerts[0]


def test_zero_signals_alerts_even_when_parsing_succeeded():
    alerts = synthesis_alerts(telegram_summary="Quiet week.", signal_count=0, raw_length=900)
    assert len(alerts) == 1
    assert "0 signals" in alerts[0]


def test_near_ceiling_alerts():
    alerts = synthesis_alerts(
        telegram_summary="Real summary.", signal_count=3, raw_length=int(BUDGET * 0.85)
    )
    assert len(alerts) == 1
    assert "ceiling" in alerts[0]


def test_failure_and_near_ceiling_both_reported():
    alerts = synthesis_alerts(
        telegram_summary=SYNTHESIS_FAILED_NOTICE,
        signal_count=0,
        raw_length=int(BUDGET * 0.95),
    )
    assert len(alerts) == 2


def test_failure_notice_and_zero_signals_do_not_double_report():
    # A failed parse always has 0 signals; reporting both would be noise.
    alerts = synthesis_alerts(
        telegram_summary=SYNTHESIS_FAILED_NOTICE, signal_count=0, raw_length=10
    )
    assert not any("0 signals" in a for a in alerts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_alerts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.research.alerts'`.

- [ ] **Step 3: Write the implementation**

```python
# src/cosinabox/research/alerts.py
"""Post-synthesis health checks.

"The job ran" is not a success signal. Both shapes below were recorded in the
legacy system's job history when they happened, and neither alerted — so a
failed digest sat unnoticed for two weeks until the next one failed the same
way. These checks exist to turn that silence into a page.
"""

from __future__ import annotations

from cosinabox import defaults
from cosinabox.research.synthesizer import SYNTHESIS_FAILED_NOTICE


def synthesis_alerts(
    *, telegram_summary: str, signal_count: int, raw_length: int
) -> list[str]:
    """Reasons this run deserves a human look. Empty when healthy."""
    alerts: list[str] = []

    if telegram_summary.strip().startswith(SYNTHESIS_FAILED_NOTICE):
        alerts.append(
            f"Synthesis produced no parseable output ({raw_length} chars). "
            "The digest shipped the failure notice."
        )
    elif signal_count == 0:
        # A quiet week is legitimate, but it looks identical to a silent
        # regression, so it is worth one glance either way.
        alerts.append(
            f"Synthesis parsed cleanly but found 0 signals ({raw_length} chars). "
            "Either a genuinely quiet week or a silent regression."
        )

    budget = defaults.RESEARCH_SYNTHESIS_MAX_TOKENS * defaults.RESEARCH_SYNTHESIS_CHARS_PER_TOKEN
    if raw_length >= budget * defaults.RESEARCH_SYNTHESIS_WARN_RATIO:
        alerts.append(
            f"Synthesis output is {raw_length} chars, {raw_length / budget:.0%} of the "
            f"~{int(budget)}-char ceiling. Trim the prompt's output contract "
            "before it truncates."
        )

    return alerts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_alerts.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit and open the milestone PR**

```bash
git add src/cosinabox/research/alerts.py tests/unit/test_research_alerts.py
git commit -m "feat(research): alert on zero-signal and near-ceiling synthesis"
pytest -q && ruff check src tests && ruff format --check src tests && mypy src/cosinabox
git push -u origin feat/research-synthesis
gh pr create --title "feat(research): streamed synthesis + health alerts" \
  --body "Milestone 4 of docs/plans/2026-08-20-port-intel-core.md" \
  && gh pr merge --auto --squash
```

---

# Milestone 5 — Persistence and delivery

Branch: `feat/research-job`. PR at the end of Task 12.

### Task 10: `research_signals` and `research_dedup` tables

**Files:**
- Modify: `src/cosinabox/memory/sqlite.py`
- Test: `tests/unit/test_research_store.py`

**Interfaces:**
- Consumes: the existing `Memory` class and its schema string.
- Produces on `Memory`:
  - `save_research_signals(signals: list[dict], *, week_of: str) -> int`
  - `research_signal_count(*, week_of: str) -> int`
  - `save_research_dedup(entries: list[dict], *, week_of: str) -> None`
  - `load_research_dedup(*, now: datetime, ttl_days: int, cap: int) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_store.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cosinabox.memory import Memory

NOW = datetime(2026, 8, 20, tzinfo=UTC)


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


def test_signals_persist_and_count_per_week(mem):
    written = mem.save_research_signals(
        [
            {"headline": "H1", "source_url": "https://x/1", "entity": "Org Alpha", "why_it_matters": "w"},
            {"headline": "H2", "source_url": "https://x/2", "entity": "Org Beta", "why_it_matters": "w"},
        ],
        week_of="2026-08-17",
    )
    assert written == 2
    assert mem.research_signal_count(week_of="2026-08-17") == 2
    assert mem.research_signal_count(week_of="2026-08-10") == 0


def test_saving_the_same_url_twice_in_a_week_is_idempotent(mem):
    row = {"headline": "H", "source_url": "https://x/1", "entity": "E", "why_it_matters": "w"}
    mem.save_research_signals([row], week_of="2026-08-17")
    mem.save_research_signals([row], week_of="2026-08-17")
    assert mem.research_signal_count(week_of="2026-08-17") == 1


def test_malformed_signal_rows_are_skipped_not_fatal(mem):
    written = mem.save_research_signals(
        ["not a dict", {"headline": "ok", "source_url": "https://x/9"}, {}],
        week_of="2026-08-17",
    )
    # The string and the keyless dict are skipped; the usable row lands.
    assert written == 1


def test_dedup_round_trips(mem):
    mem.save_research_dedup(
        [{"url": "https://x/1", "headline": "H1"}], week_of="2026-08-17"
    )
    loaded = mem.load_research_dedup(now=NOW, ttl_days=30, cap=150)
    assert loaded == [{"url": "https://x/1", "headline": "H1", "week_of": "2026-08-17"}]


def test_dedup_entries_older_than_the_ttl_are_dropped(mem):
    old_week = (NOW - timedelta(days=60)).date().isoformat()
    mem.save_research_dedup([{"url": "https://old", "headline": "O"}], week_of=old_week)
    mem.save_research_dedup([{"url": "https://new", "headline": "N"}], week_of="2026-08-17")
    urls = [e["url"] for e in mem.load_research_dedup(now=NOW, ttl_days=30, cap=150)]
    assert urls == ["https://new"]


def test_dedup_respects_the_cap(mem):
    for n in range(10):
        mem.save_research_dedup([{"url": f"https://x/{n}", "headline": str(n)}], week_of="2026-08-17")
    assert len(mem.load_research_dedup(now=NOW, ttl_days=30, cap=4)) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_store.py -v`
Expected: FAIL — `AttributeError: 'Memory' object has no attribute 'save_research_signals'`.

- [ ] **Step 3: Add the tables to the schema string**

In `src/cosinabox/memory/sqlite.py`, alongside the other `CREATE TABLE IF NOT EXISTS` statements:

```sql
-- Durable record of every reported research signal. This is the only place a
-- signal survives after the digest is delivered, so treat it as primary data,
-- not as a cache. UNIQUE(week_of, source_url) makes a re-run idempotent.
CREATE TABLE IF NOT EXISTS research_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_of TEXT NOT NULL,
    headline TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    entity TEXT NOT NULL DEFAULT '',
    why_it_matters TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(week_of, source_url)
);

-- What we have already reported, fed back into the next run's prompt so the
-- digest doesn't repeat itself. Pruned by age on read.
CREATE TABLE IF NOT EXISTS research_dedup (
    url TEXT PRIMARY KEY,
    headline TEXT NOT NULL DEFAULT '',
    week_of TEXT NOT NULL
);
```

- [ ] **Step 4: Add the accessors**

```python
    def save_research_signals(self, signals: list[Any], *, week_of: str) -> int:
        """Persist this week's signals. Returns the number of rows written.

        Malformed entries are skipped rather than raising: the model produces
        this list, and one bad row must not cost the whole week's record.
        """
        written = 0
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            url = str(signal.get("source_url") or "")
            headline = str(signal.get("headline") or "")
            if not url and not headline:
                continue
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO research_signals
                    (week_of, headline, source_url, entity, why_it_matters)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    week_of,
                    headline,
                    url,
                    str(signal.get("entity") or ""),
                    str(signal.get("why_it_matters") or ""),
                ),
            )
            written += cur.rowcount or 0
        self._conn.commit()
        return written

    def research_signal_count(self, *, week_of: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM research_signals WHERE week_of = ?", (week_of,)
        ).fetchone()
        return int(row[0]) if row else 0

    def save_research_dedup(self, entries: list[Any], *, week_of: str) -> None:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url") or "")
            if not url:
                continue
            self._conn.execute(
                """
                INSERT INTO research_dedup (url, headline, week_of) VALUES (?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    headline = excluded.headline, week_of = excluded.week_of
                """,
                (url, str(entry.get("headline") or ""), week_of),
            )
        self._conn.commit()

    def load_research_dedup(
        self, *, now: datetime, ttl_days: int, cap: int
    ) -> list[dict[str, str]]:
        """Recent dedup entries, newest first, pruned by age and capped.

        The cap protects the synthesis prompt's token budget — an unbounded
        index grows forever and eventually crowds out the candidates.
        """
        cutoff = (now - timedelta(days=ttl_days)).date().isoformat()
        rows = self._conn.execute(
            """
            SELECT url, headline, week_of FROM research_dedup
            WHERE week_of >= ?
            ORDER BY week_of DESC, url ASC
            LIMIT ?
            """,
            (cutoff, cap),
        ).fetchall()
        return [{"url": r[0], "headline": r[1], "week_of": r[2]} for r in rows]
```

Add `from datetime import datetime, timedelta` to the module imports if not already present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_store.py -v`
Expected: PASS (6 tests).

Also run: `pytest tests/ -k memory -v` — existing memory tests must be unaffected.

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/memory/sqlite.py tests/unit/test_research_store.py
git commit -m "feat(research): research_signals and research_dedup tables"
```

---

### Task 11: Pre-run database backup

**Files:**
- Create: `src/cosinabox/memory/backup.py`
- Modify: `src/cosinabox/defaults.py`
- Test: `tests/unit/test_memory_backup.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `backup_database(db_path: Path, *, keep: int, now: datetime) -> Path | None`

**Why this is here:** the migration note calls out that the legacy signals table was single-copy on a Railway volume and was the only source that made a historical backfill possible. The note asks for this to be solved once for the whole store, so the helper takes a database path rather than living inside the research package.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_memory_backup.py
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from cosinabox.memory.backup import backup_database

NOW = datetime(2026, 8, 20, 3, 4, 5, tzinfo=UTC)


def _db(tmp_path, name="memory.db"):
    path = tmp_path / name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    return path


def test_creates_a_timestamped_copy_that_opens(tmp_path):
    src = _db(tmp_path)
    out = backup_database(src, keep=3, now=NOW)
    assert out is not None
    assert out.name == "memory.db.20260820T030405Z.bak"
    assert out.parent == src.parent / "backups"
    conn = sqlite3.connect(out)
    assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
    conn.close()


def test_missing_source_returns_none(tmp_path):
    assert backup_database(tmp_path / "nope.db", keep=3, now=NOW) is None


def test_prunes_to_the_keep_count_oldest_first(tmp_path):
    src = _db(tmp_path)
    made = []
    for minute in range(5):
        made.append(
            backup_database(src, keep=3, now=NOW.replace(minute=minute))
        )
    remaining = sorted(p.name for p in (src.parent / "backups").iterdir())
    assert len(remaining) == 3
    # The three most recent survive.
    assert remaining == sorted(p.name for p in made[-3:])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory_backup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.memory.backup'`.

- [ ] **Step 3: Add the default**

```python
# Rolling database backups kept on disk. The store holds primary data —
# research signals, commitments, autonomy history — on a single volume, so a
# volume loss with no copy is unrecoverable. Seven daily-ish copies is a week
# of runway at a few MB each. (2026-08-20)
MEMORY_BACKUP_KEEP: int = 7
```

- [ ] **Step 4: Write the implementation**

```python
# src/cosinabox/memory/backup.py
"""Rolling on-disk backups of the SQLite store.

The store holds primary data, not a cache: research signals exist nowhere else
once a digest is delivered. A single volume with no copy makes any loss
unrecoverable, which is why this runs before the weekly job writes.

Uses SQLite's own backup API rather than a file copy so a concurrent writer
cannot produce a torn snapshot.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from cosinabox import defaults

logger = logging.getLogger(__name__)

_SUFFIX = ".bak"


def backup_database(
    db_path: Path, *, keep: int = defaults.MEMORY_BACKUP_KEEP, now: datetime | None = None
) -> Path | None:
    """Write a consistent copy of `db_path` into a sibling `backups/` dir.

    Returns the backup path, or None when there is nothing to back up.
    Prunes to the `keep` most recent copies.
    """
    if not db_path.exists():
        logger.info("No database at %s — nothing to back up", db_path)
        return None

    now = now or datetime.now(tz=None)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = db_path.parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{db_path.name}.{stamp}{_SUFFIX}"

    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(out_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    existing = sorted(
        (p for p in out_dir.iterdir() if p.name.startswith(db_path.name) and p.suffix == _SUFFIX),
        key=lambda p: p.name,
    )
    for stale in existing[:-keep] if keep > 0 else existing:
        stale.unlink(missing_ok=True)
        logger.info("Pruned old backup %s", stale.name)

    logger.info("Database backed up to %s", out_path)
    return out_path
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_memory_backup.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/memory/backup.py src/cosinabox/defaults.py \
        tests/unit/test_memory_backup.py
git commit -m "feat(memory): rolling SQLite backups via the sqlite backup API"
```

---

### Task 12: `ResearchDigestJob` and registration

**Files:**
- Create: `src/cosinabox/jobs/research_digest.py`
- Modify: `src/cosinabox/app/jobs.py`
- Modify: `src/cosinabox/templates/user-repo/jobs.yaml`
- Test: `tests/unit/test_research_digest_job.py`

**Interfaces:**
- Consumes: everything above — `ResearchConfig.load`, `collect`, `read_feeds`, `classify`, `synthesize`, `synthesis_alerts`, `Memory.save_research_signals` / `save_research_dedup` / `load_research_dedup`, `backup_database`.
- Produces: `ResearchDigestJob(Job)` with `name = "research_digest"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_research_digest_job.py
from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.research_digest import ResearchDigestJob
from cosinabox.memory import Memory

CONFIG = textwrap.dedent(
    """
    schema_version: 1
    groups:
      - name: labs
        priority: 0
        search: {country: us, topic: news, time_range: week}
        entities:
          - name: Org Alpha
            queries: ["Org Alpha launch"]
    feeds: []
    field_queries: []
    """
)

SYNTH = {
    "telegram_summary": "Org Alpha shipped a thing.",
    "full_report": "# Report",
    "signal_records": [
        {"headline": "Org Alpha shipped", "source_url": "https://x/1", "entity": "Org Alpha"}
    ],
    "follow_up_signals": [],
}


@pytest.fixture
def wired(tmp_path, monkeypatch):
    (tmp_path / "research.yaml").write_text(CONFIG)
    mem = Memory(db_path=tmp_path / "memory.db")
    sent: list[str] = []

    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.collect",
        lambda cfg, **kw: SimpleNamespace(
            items=[{"title": "T", "url": "https://x/1", "snippet": "", "source": "x"}],
            search_failed=False,
            counts={"raw": 1, "capped": 1},
        ),
    )
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.classify", lambda items, **kw: items
    )
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.synthesize",
        lambda cfg, **kw: (dict(SYNTH), "{}"),
    )

    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=mem,
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=sent.append,
        notify_error=sent.append,
        model="claude-sonnet-5",
    )
    return job, mem, sent


def test_missing_config_reports_not_configured(tmp_path):
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=None,
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=lambda m: None,
        notify_error=lambda m: None,
        model="m",
    )
    result = job.run(JobContext())
    assert "not configured" in result.lower()


def test_missing_api_key_reports_not_configured(tmp_path):
    (tmp_path / "research.yaml").write_text(CONFIG)
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=None,
        anthropic_client=SimpleNamespace(),
        search_api_key="",
        send_telegram=lambda m: None,
        notify_error=lambda m: None,
        model="m",
    )
    assert "not configured" in job.run(JobContext()).lower()


def test_happy_path_sends_summary_and_persists_signals(wired):
    job, mem, sent = wired
    result = job.run(JobContext())

    assert any("Org Alpha shipped a thing." in m for m in sent)
    assert "1 signal" in result
    # Signals and the dedup index both persisted.
    week = job._week_of()
    assert mem.research_signal_count(week_of=week) == 1
    assert [e["url"] for e in mem.load_research_dedup(now=job._now(), ttl_days=30, cap=10)] == [
        "https://x/1"
    ]


def test_total_search_failure_notifies_and_does_not_synthesize(tmp_path, monkeypatch):
    (tmp_path / "research.yaml").write_text(CONFIG)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.collect",
        lambda cfg, **kw: SimpleNamespace(items=[], search_failed=True, counts={"raw": 0}),
    )

    def _must_not_run(*a, **kw):
        raise AssertionError("synthesis must not run without candidates")

    monkeypatch.setattr("cosinabox.jobs.research_digest.synthesize", _must_not_run)
    errors: list[str] = []
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=Memory(db_path=tmp_path / "m.db"),
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=lambda m: None,
        notify_error=errors.append,
        model="m",
    )
    result = job.run(JobContext())
    assert errors and "search" in errors[0].lower()
    assert "no candidates" in result.lower()


def test_alerts_are_routed_to_notify_error(tmp_path, monkeypatch):
    (tmp_path / "research.yaml").write_text(CONFIG)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.collect",
        lambda cfg, **kw: SimpleNamespace(
            items=[{"title": "T", "url": "https://x/1"}], search_failed=False, counts={}
        ),
    )
    monkeypatch.setattr("cosinabox.jobs.research_digest.classify", lambda items, **kw: items)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.synthesize",
        lambda cfg, **kw: ({**SYNTH, "signal_records": []}, "{}"),
    )
    errors: list[str] = []
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=Memory(db_path=tmp_path / "m.db"),
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=lambda m: None,
        notify_error=errors.append,
        model="m",
    )
    job.run(JobContext())
    # Zero signals must page, not pass silently.
    assert errors and "0 signals" in errors[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_research_digest_job.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cosinabox.jobs.research_digest'`.

- [ ] **Step 3: Write the implementation**

```python
# src/cosinabox/jobs/research_digest.py
"""Weekly research digest: collect -> classify -> synthesize -> store -> notify."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cosinabox import defaults
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
            self.notify_error(
                "research_digest: every search query failed — no digest this week."
            )
            return "research_digest: search failed, no candidates collected."
        if not result.items:
            self.notify_error("research_digest: collection produced no candidates.")
            return "research_digest: no candidates collected."

        items = classify(
            result.items, entity_names=cfg.entity_names(), client=self.client
        )

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
```

- [ ] **Step 4: Register the job**

In `src/cosinabox/app/jobs.py`, following the `post_meeting_debrief` pattern:

```python
        elif job_name == "research_digest":
            from cosinabox.jobs.research_digest import ResearchDigestJob

            job = ResearchDigestJob(
                config_dir=config_dir,
                db=memory,
                anthropic_client=anthropic_factory(),
                search_api_key=os.environ.get("TAVILY_API_KEY", ""),
                send_telegram=send_telegram,
                notify_error=notify_error,
                model=loop.model,
            )
            cron = cfg.get("schedule", "30 8 * * 1")
            scheduler.add_job(job, cron=cron, timezone=cfg.get("timezone"))
            logger.info("Registered %s at %s", job_name, cron)
```

Match the surrounding code for how `send_telegram`, `notify_error`, `config_dir` and `loop.model` are actually obtained in that function — read it before writing, and reuse the existing locals rather than introducing new ones.

In `src/cosinabox/templates/user-repo/jobs.yaml`:

```yaml
  research_digest:
    enabled: false
    schedule: "30 8 * * 1"     # Mon 8:30 AM — weekly digest; needs research.yaml
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_research_digest_job.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Document the job**

Add a `research_digest` row to `src/cosinabox/templates/user-repo/docs/agent/jobs.md` describing what it does, that it requires `research.yaml` plus `TAVILY_API_KEY` and the `[research]` extra, and what is lost when it is disabled (CLAUDE.md OSS rules 2–4: a feature only findable in source does not exist, and fallbacks must be explicit).

- [ ] **Step 7: Commit and open the milestone PR**

```bash
git add src/cosinabox/jobs/research_digest.py src/cosinabox/app/jobs.py \
        src/cosinabox/templates/user-repo/jobs.yaml \
        src/cosinabox/templates/user-repo/docs/agent/jobs.md \
        tests/unit/test_research_digest_job.py
git commit -m "feat(research): research_digest job wiring and registration"
pytest -q && ruff check src tests && ruff format --check src tests && mypy src/cosinabox
git push -u origin feat/research-job
gh pr create --title "feat(research): research_digest job" \
  --body "Milestone 5 of docs/plans/2026-08-20-port-intel-core.md" \
  && gh pr merge --auto --squash
```

---

## After the plan

1. **Update the cutover inventory.** In `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md`, change the intel row's fate from `port (decided 2026-08-18)` to `ported (core) YYYY-MM-DD` and note that publication is still outstanding. The cutover trigger reads that table.
2. **Write the retro** in `docs/retros/` (CLAUDE.md safety rule 6: per-plan retro).
3. **Add the CHANGELOG entry** under `## [Unreleased]`, `### Added`.
4. **Do not disable the legacy job yet.** Run both for at least two weeks and compare digests; the legacy pipeline stays the source of truth until the ported one has produced comparable output. Only then does cos-agent's `asia_lab_tracker` get switched off.
5. **Then plan the publication milestone** (`digest_publisher`), carrying the #187 failed-read scar noted at the top.

## Self-review notes

- **Spec coverage.** Migration-note items: streamed synthesis → Task 7/8; alert on zero-signal and near-ceiling → Task 9; signals as the durable record with a backup → Tasks 10/11; failed-read-is-not-empty-file → explicitly deferred with the publication plan and restated there; dead-man's switch → explicitly deferred as scheduler-wide with the reason given.
- **Known gap, stated deliberately.** Stage 3 (follow-up searches on flagged signals) is not ported. `follow_up_signals` is captured by synthesis and stored, but nothing acts on it yet. It is a genuine feature loss versus the legacy pipeline — add it as a task in the publication plan, where its output has somewhere to go.
- **Type consistency.** `SearchSpec` / `Query` / `Group` / `Entity` / `ResearchConfig` are defined in Task 2 and used unchanged in Tasks 4, 6, 8. `SearchBackend.__call__` in Task 4 matches `TavilyTool.search` in Task 3 exactly. `FeedReader` in Task 4 matches `read_feeds` in Task 5 once `now` is bound. `synthesis_alerts` in Task 9 consumes the `(telegram_summary, signal_count, raw_length)` triple the job assembles in Task 12.
- **Registration is the one place to read before writing.** Task 12's `app/jobs.py` snippet assumes locals (`send_telegram`, `notify_error`, `config_dir`, `loop.model`, `os`) that the surrounding registration function may name differently. Every other task's code is self-contained; this one is not.
