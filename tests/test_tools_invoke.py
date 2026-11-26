"""Drive the tools through ``_invoke`` with a real ``ToolRuntime`` and a mocked
network, so endpoint selection, headers, the SSRF guard, and the emitted
message types are all exercised the way the Dify runtime would call them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dify_plugin.entities.tool import ToolInvokeMessage, ToolRuntime  # noqa: E402

import utils.keenable_client as kc  # noqa: E402
from tools.keenable_fetch import KeenableFetchTool  # noqa: E402
from tools.keenable_search import KeenableSearchTool  # noqa: E402

TEXT = ToolInvokeMessage.MessageType.TEXT
JSON = ToolInvokeMessage.MessageType.JSON


class FakeResp:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


def _runtime(key=""):
    return ToolRuntime(credentials={"keenable_api_key": key}, user_id="u", session_id="s")


def test_search_keyless_emits_json_and_text(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers, payload=json)
        # A realistic result: the API returns both fields, `description` is
        # frequently empty and `snippet` carries the page text.
        return FakeResp(
            {"results": [{"title": "A", "url": "https://a.com", "description": "", "snippet": "page text"}]}
        )

    monkeypatch.setattr(kc.requests, "post", fake_post)
    msgs = list(KeenableSearchTool(runtime=_runtime(), session=None)._invoke({"query": "cats"}))

    assert seen["url"].endswith("/v1/search/public")  # keyless
    assert seen["headers"]["X-Keenable-Title"] == "Dify"
    assert "X-API-Key" not in seen["headers"]
    assert [m.type for m in msgs] == [JSON, TEXT]


def test_search_passes_filters(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        kc.requests, "post",
        lambda url, json=None, headers=None, timeout=None: (
            seen.update(payload=json) or FakeResp({"results": [{"url": "https://a.com"}]})
        ),
    )
    list(
        KeenableSearchTool(runtime=_runtime(), session=None)._invoke(
            {"query": "q", "mode": "realtime", "site": "github.com", "published_after": "2026-01-01"}
        )
    )
    assert seen["payload"] == {
        "query": "q", "mode": "realtime", "site": "github.com", "published_after": "2026-01-01"
    }


def _search_payload(monkeypatch, params):
    seen = {}
    monkeypatch.setattr(
        kc.requests, "post",
        lambda url, json=None, headers=None, timeout=None: (
            seen.update(payload=json) or FakeResp({"results": [{"url": "https://a.com"}]})
        ),
    )
    list(KeenableSearchTool(runtime=_runtime(), session=None)._invoke(params))
    return seen["payload"]


def test_search_objective_is_sent_trimmed(monkeypatch):
    payload = _search_payload(monkeypatch, {"query": "q", "objective": "  Find the 2026 pricing.  "})
    assert payload["objective"] == "Find the 2026 pricing."


def test_search_blank_objective_is_not_sent(monkeypatch):
    assert "objective" not in _search_payload(monkeypatch, {"query": "q", "objective": "  "})


def test_search_overlong_objective_short_circuits(monkeypatch):
    monkeypatch.setattr(kc.requests, "post", lambda *a, **k: pytest.fail("should not call API"))
    msgs = list(KeenableSearchTool(runtime=_runtime(), session=None)._invoke({"query": "q", "objective": "x" * 1001}))
    assert [m.type for m in msgs] == [TEXT]
    assert "1000" in msgs[0].message.text


def test_search_objective_at_limit_is_sent(monkeypatch):
    payload = _search_payload(monkeypatch, {"query": "q", "objective": " " + "x" * 1000 + " "})
    assert len(payload["objective"]) == 1000


def test_search_empty_query_short_circuits(monkeypatch):
    monkeypatch.setattr(kc.requests, "post", lambda *a, **k: pytest.fail("should not call API"))
    msgs = list(KeenableSearchTool(runtime=_runtime(), session=None)._invoke({"query": "  "}))
    assert [m.type for m in msgs] == [TEXT]


def test_fetch_keyed_emits_json_and_text(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, payload=json, headers=headers)
        return FakeResp({"results": [{"content": "# A", "url": "https://a.com", "title": "A"}]})

    monkeypatch.setattr(kc.requests, "post", fake_post)
    msgs = list(KeenableFetchTool(runtime=_runtime("keen_x"), session=None)._invoke({"url": "https://a.com"}))

    assert seen["url"].endswith("/v1/fetch")  # keyed
    assert seen["headers"]["X-API-Key"] == "keen_x"
    assert seen["payload"] == {"urls": ["https://a.com"]}
    assert [m.type for m in msgs] == [JSON, TEXT]


@pytest.mark.parametrize("url", ["http://169.254.169.254/x", "ftp://x", "http://localhost/x"])
def test_fetch_rejects_unsafe_urls_without_calling_api(monkeypatch, url):
    monkeypatch.setattr(kc.requests, "post", lambda *a, **k: pytest.fail("should not call API"))
    msgs = list(KeenableFetchTool(runtime=_runtime(), session=None)._invoke({"url": url}))
    assert [m.type for m in msgs] == [TEXT]


def test_search_api_error_surfaces_as_text(monkeypatch):
    monkeypatch.setattr(
        kc.requests, "post",
        lambda *a, **k: type("R", (), {
            "ok": False, "status_code": 429, "text": "",
            "json": lambda self: {"message": "slow down"},
        })(),
    )
    msgs = list(KeenableSearchTool(runtime=_runtime(), session=None)._invoke({"query": "q"}))
    assert [m.type for m in msgs] == [TEXT]
    assert "rate limit" in str(msgs[0].message).lower()


def test_digest_reads_snippet_with_description_fallback():
    from tools.keenable_search import _format_results

    digest = _format_results(
        "q",
        [
            {"title": "A", "url": "https://a.com", "description": "", "snippet": "page text"},
            {"title": "B", "url": "https://b.com", "description": "a description"},
        ],
    )

    assert "page text" in digest
    assert "a description" in digest


def test_digest_collapses_whitespace_and_caps_the_snippet():
    # Snippets are raw page text: newlines would break the one-line-per-field
    # layout, and they run far longer than the digest should carry.
    from tools.keenable_search import MAX_SNIPPET_CHARS, _result_snippet

    snippet = _result_snippet({"snippet": "line one\n\nline two" + " padding" * 500})

    assert len(snippet) == MAX_SNIPPET_CHARS
    assert "\n" not in snippet
    assert snippet.startswith("line one line two")


def test_plugin_version_matches_manifest():
    import yaml

    manifest = yaml.safe_load((Path(__file__).resolve().parent.parent / "manifest.yaml").read_text())
    assert kc.PLUGIN_VERSION == manifest["version"]


def test_search_tool_level_llm_description_mentions_objective():
    import yaml

    spec = yaml.safe_load((Path(__file__).resolve().parent.parent / "tools" / "keenable_search.yaml").read_text())
    assert "objective" in spec["description"]["llm"]
    objective = next(p for p in spec["parameters"] if p["name"] == "objective")
    assert len(objective["llm_description"]) < 400
