"""Shared transport for the Keenable Dify plugin.

One place for the parts of the Keenable contract both tools need: keyed-vs-keyless
endpoint selection, the attribution headers, HTTPS-only base-URL resolution, the
client-side SSRF guard, and turning a non-2xx response into a readable error. The
endpoint comes from the environment, never a tool argument the LLM can set (an
arbitrary base URL is an SSRF foothold).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from typing import Any
from urllib.parse import urlsplit

import requests

# Bumped together with manifest.yaml `version`. Kept as a literal because a Dify
# plugin is not pip-installed, so importlib.metadata cannot see a package version.
PLUGIN_VERSION = "0.1.1"

# Tagged User-Agent so Keenable can attribute traffic from this integration.
_USER_AGENT = f"keenable-dify/{PLUGIN_VERSION}"

# The load-bearing attribution signal: the Keenable backend segments traffic by
# this header (adoption dashboards). The User-Agent above is a secondary tag.
_ATTRIBUTION_TITLE = "Dify"

_DEFAULT_BASE_URL = "https://api.keenable.ai"
_BASE_URL_ENV = "KEENABLE_API_URL"


class KeenableError(RuntimeError):
    """A Keenable transport/API error carrying a message safe to show a user."""


def _candidate_ips(host: str) -> list:
    """Every IP address ``host`` could denote, without doing DNS.

    Covers dotted/colon literals AND the legacy/alternate IPv4 encodings the OS
    resolver accepts but ``ipaddress.ip_address`` rejects as strings -- decimal
    (``2130706433``), hex (``0x7f000001``), octal (``0177.0.0.1``) and short
    (``127.1``) forms -- all canonicalized via ``socket.inet_aton``.
    """
    candidates = []
    try:
        candidates.append(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        packed = socket.inet_aton(host)
    except OSError:
        pass
    else:
        candidates.append(ipaddress.ip_address(socket.inet_ntoa(packed)))
    return candidates


def _is_private_ip(ip) -> bool:
    # ``is_reserved`` is intentionally omitted -- it flags non-routable but
    # harmless ranges (e.g. the 2001:db8::/32 docs prefix). These are the checks
    # that matter for SSRF.
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    )


def resolve_base_url() -> str:
    """Resolve the API base URL from ``KEENABLE_API_URL`` and enforce HTTPS."""
    base = (os.environ.get(_BASE_URL_ENV) or _DEFAULT_BASE_URL).rstrip("/")
    parsed = urlsplit(base)
    host = (parsed.hostname or "").rstrip(".")
    if not host:
        msg = f"{_BASE_URL_ENV} must be an https:// URL with a host, got {base!r}"
        raise KeenableError(msg)
    # Local-dev escape hatch: plain http only to an explicit loopback host.
    if parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        return base
    if parsed.scheme != "https":
        msg = f"{_BASE_URL_ENV} must be an https:// URL with a host, got {base!r}"
        raise KeenableError(msg)
    # Over https, refuse a base URL pointing at a private/internal destination --
    # a misconfigured KEENABLE_API_URL must never ship API keys to an internal host.
    if host == "metadata.google.internal" or any(_is_private_ip(ip) for ip in _candidate_ips(host)):
        msg = f"{_BASE_URL_ENV} must not point at a private/internal address, got {base!r}"
        raise KeenableError(msg)
    return base


def reject_private_fetch_target(url: str) -> None:
    """Refuse obviously private/internal fetch targets before sending (SSRF).

    The backend enforces this server-side too, but a client-side guard avoids
    leaking an internal hostname in a request and is required by our integration
    contract. Hostnames that are not IP literals (and not a numeric IPv4 form)
    pass through; the backend's SSRF guard is the backstop for those.
    """
    host = (urlsplit(url).hostname or "").strip().lower()
    # A trailing dot is the FQDN form of the same name (``localhost.`` ==
    # ``localhost``); strip it so it can't slip past the checks below.
    host = host.rstrip(".")
    if not host:
        msg = f"Refusing to fetch a URL with no host: {url!r}"
        raise KeenableError(msg)
    if host in {"localhost", "metadata.google.internal"}:
        msg = f"Refusing to fetch a private/internal host: {host!r}"
        raise KeenableError(msg)
    for ip in _candidate_ips(host):
        if _is_private_ip(ip):
            msg = f"Refusing to fetch a private/internal address: {host!r}"
            raise KeenableError(msg)


def resolve_api_key(raw: str | None) -> str | None:
    """The non-blank key, else ``KEENABLE_API_KEY``, else ``None`` (keyless)."""
    key = raw.strip() if isinstance(raw, str) else ""
    if not key:
        key = (os.environ.get("KEENABLE_API_KEY") or "").strip()
    return key or None


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"User-Agent": _USER_AGENT, "X-Keenable-Title": _ATTRIBUTION_TITLE}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _raise_for_status(response: requests.Response) -> None:
    """Map a non-2xx Keenable response to a readable :class:`KeenableError`."""
    if response.ok:
        return
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("error") or body.get("detail") or "")
    except ValueError:
        detail = (response.text or "").strip()
    detail = _redact_secrets(detail)
    label = {
        401: "Keenable authentication failed (401)",
        402: "Keenable: insufficient credits (402)",
        429: "Keenable rate limit exceeded (429); set an API key to raise limits",
    }.get(response.status_code, f"Keenable API error ({response.status_code})")
    raise KeenableError(f"{label}: {detail}" if detail else label)


def _redact_secrets(text: str) -> str:
    """Mask any Keenable API key that an error body might echo back.

    Error detail is surfaced to the model/logs, so defensively scrub anything in
    the ``keen_<token>`` shape rather than trust the API never to reflect a key.
    """
    return re.sub(r"keen_[A-Za-z0-9_-]{4,}", "keen_***", text)


def _decode(response: requests.Response) -> dict[str, Any]:
    _raise_for_status(response)
    try:
        data = response.json()
    except ValueError as e:
        snippet = _redact_secrets((response.text or "")[:200])
        msg = f"Keenable API returned a non-JSON response: {snippet!r}"
        raise KeenableError(msg) from e
    if not isinstance(data, dict):
        msg = f"Unexpected response from the Keenable API: {_redact_secrets(repr(data)[:200])}"
        raise KeenableError(msg)
    return data


def _transport_error(e: Exception) -> KeenableError:
    """Wrap a transport exception, scrubbing any echoed key from its message.

    A custom adapter/proxy could surface a header in the exception string; mask
    anything in the ``keen_<token>`` shape rather than emit the raw repr.
    """
    return KeenableError(
        f"Could not reach the Keenable API: {type(e).__name__}: {_redact_secrets(str(e))}"
    )


def keenable_post(
    public_path: str, keyed_path: str, payload: dict[str, Any], api_key: str | None, timeout: float
) -> dict[str, Any]:
    """POST ``payload`` to the keyed or keyless endpoint and return the body."""
    path = keyed_path if api_key else public_path
    url = f"{resolve_base_url()}{path}"
    headers = {**_headers(api_key), "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise _transport_error(e) from e
    return _decode(response)


def keenable_get(
    public_path: str, keyed_path: str, params: dict[str, Any], api_key: str | None, timeout: float
) -> dict[str, Any]:
    """GET the keyed or keyless endpoint with query ``params``; return the body."""
    path = keyed_path if api_key else public_path
    url = f"{resolve_base_url()}{path}"
    try:
        response = requests.get(url, params=params, headers=_headers(api_key), timeout=timeout)
    except requests.RequestException as e:
        raise _transport_error(e) from e
    return _decode(response)
