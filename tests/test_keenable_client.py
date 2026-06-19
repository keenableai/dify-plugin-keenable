"""Offline tests for the Keenable Dify plugin transport + helpers.

These cover the security-critical and contract surface without a live Dify
runtime: endpoint selection (keyed vs keyless), attribution headers, HTTPS-only
base-URL resolution, the client-side SSRF guard, error mapping, and the search
result formatter. The network is mocked at the ``requests`` boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Put the plugin root on sys.path so `utils...` and `tools...` resolve the same
# way the Dify runtime loads them (entrypoint = main.py at the root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import keenable_client as kc  # noqa: E402
from tools.keenable_search import _format_results  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._json_body is None:
            raise ValueError("no json")
        return self._json_body


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    monkeypatch.delenv("KEENABLE_API_URL", raising=False)


# --- base URL resolution -------------------------------------------------

def test_base_url_default():
    assert kc.resolve_base_url() == "https://api.keenable.ai"


def test_base_url_https_override(monkeypatch):
    monkeypatch.setenv("KEENABLE_API_URL", "https://proxy.example.com/")
    assert kc.resolve_base_url() == "https://proxy.example.com"


def test_base_url_http_loopback_allowed(monkeypatch):
    monkeypatch.setenv("KEENABLE_API_URL", "http://127.0.0.1:8080")
    assert kc.resolve_base_url() == "http://127.0.0.1:8080"


@pytest.mark.parametrize("bad", ["http://api.keenable.ai", "ftp://x", "https://", "not-a-url"])
def test_base_url_rejects_non_https(monkeypatch, bad):
    monkeypatch.setenv("KEENABLE_API_URL", bad)
    with pytest.raises(kc.KeenableError):
        kc.resolve_base_url()


# --- API key resolution --------------------------------------------------

def test_resolve_api_key_prefers_arg():
    assert kc.resolve_api_key("  keen_abc ") == "keen_abc"


def test_resolve_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("KEENABLE_API_KEY", "keen_env")
    assert kc.resolve_api_key("   ") == "keen_env"
    assert kc.resolve_api_key(None) == "keen_env"


def test_resolve_api_key_blank_is_keyless():
    assert kc.resolve_api_key("   ") is None
    assert kc.resolve_api_key(None) is None


# --- SSRF guard ----------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://127.0.0.1/x",
        "https://10.0.0.5/x",
        "https://192.168.1.1/x",
        "https://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/x",
        "https://[::1]/x",
        "not-a-url-no-host",
    ],
)
def test_reject_private_fetch_target(url):
    with pytest.raises(kc.KeenableError):
        kc.reject_private_fetch_target(url)


@pytest.mark.parametrize("url", ["https://example.com/x", "https://github.com/a/b"])
def test_allows_public_fetch_target(url):
    kc.reject_private_fetch_target(url)  # no raise


# --- endpoint selection + attribution headers ----------------------------

def test_post_keyless_uses_public_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, headers=headers)
        return FakeResponse(json_body={"results": []})

    monkeypatch.setattr(kc.requests, "post", fake_post)
    kc.keenable_post("/v1/search/public", "/v1/search", {"query": "x"}, None, 10.0)

    assert captured["url"] == "https://api.keenable.ai/v1/search/public"
    assert captured["headers"]["X-Keenable-Title"] == "Dify"
    assert captured["headers"]["User-Agent"].startswith("keenable-dify/")
    assert "X-API-Key" not in captured["headers"]


def test_post_keyed_uses_authenticated_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, headers=headers)
        return FakeResponse(json_body={"results": []})

    monkeypatch.setattr(kc.requests, "post", fake_post)
    kc.keenable_post("/v1/search/public", "/v1/search", {"query": "x"}, "keen_k", 10.0)

    assert captured["url"] == "https://api.keenable.ai/v1/search"
    assert captured["headers"]["X-API-Key"] == "keen_k"


def test_get_keyed_endpoint_and_params(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured.update(url=url, params=params, headers=headers)
        return FakeResponse(json_body={"content": "hi"})

    monkeypatch.setattr(kc.requests, "get", fake_get)
    out = kc.keenable_get("/v1/fetch/public", "/v1/fetch", {"url": "https://e.com"}, "k", 10.0)

    assert captured["url"] == "https://api.keenable.ai/v1/fetch"
    assert captured["params"] == {"url": "https://e.com"}
    assert out == {"content": "hi"}


# --- error mapping -------------------------------------------------------

@pytest.mark.parametrize(
    "status,needle",
    [(401, "authentication"), (402, "credits"), (429, "rate limit"), (500, "500")],
)
def test_error_status_mapping(monkeypatch, status, needle):
    monkeypatch.setattr(
        kc.requests, "post",
        lambda *a, **k: FakeResponse(status_code=status, json_body={"message": "boom"}),
    )
    with pytest.raises(kc.KeenableError) as e:
        kc.keenable_post("/v1/search/public", "/v1/search", {}, None, 10.0)
    assert needle in str(e.value).lower()
    assert "boom" in str(e.value)


def test_non_json_body_raises(monkeypatch):
    monkeypatch.setattr(
        kc.requests, "post", lambda *a, **k: FakeResponse(status_code=200, text="<html>")
    )
    with pytest.raises(kc.KeenableError):
        kc.keenable_post("/v1/search/public", "/v1/search", {}, None, 10.0)


def test_network_error_wrapped(monkeypatch):
    def boom(*a, **k):
        raise kc.requests.RequestException("dns")

    monkeypatch.setattr(kc.requests, "post", boom)
    with pytest.raises(kc.KeenableError) as e:
        kc.keenable_post("/v1/search/public", "/v1/search", {}, None, 10.0)
    assert "could not reach" in str(e.value).lower()


# --- search result formatting -------------------------------------------

def test_format_results_renders_fields():
    out = _format_results(
        "cats",
        [{"title": "T", "url": "https://e.com", "description": "D", "published_at": "2026-01-01"}],
    )
    assert "1. T" in out
    assert "https://e.com" in out
    assert "2026-01-01" in out
    assert "D" in out


def test_format_results_handles_missing_fields():
    out = _format_results("x", [{"url": "https://e.com"}])
    assert "https://e.com" in out  # title falls back to url, no crash
