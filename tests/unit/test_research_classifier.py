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
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))


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
