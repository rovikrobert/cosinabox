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
