from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.keenable_client import KeenableError, keenable_post, resolve_api_key

# Keenable returns whole-page text where other engines return a short snippet,
# so cap what goes into the digest the model reads.
MAX_SNIPPET_CHARS = 500


class KeenableSearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        query = (tool_parameters.get("query") or "").strip()
        if not query:
            yield self.create_text_message("Please provide a search query.")
            return

        api_key = resolve_api_key(self.runtime.credentials.get("keenable_api_key"))
        payload: dict[str, Any] = {"query": query, "mode": tool_parameters.get("mode") or "pro"}
        for field in ("site", "published_after", "published_before"):
            value = tool_parameters.get(field)
            if value:
                payload[field] = value

        try:
            data = keenable_post(
                "/v1/search/public", "/v1/search", payload, api_key, timeout=30.0
            )
        except KeenableError as e:
            yield self.create_text_message(str(e))
            return

        results = data.get("results")
        if not isinstance(results, list) or not results:
            yield self.create_text_message(f"No results found for {query!r}.")
            return

        # Structured output for workflow `json`, plus a human/LLM-readable digest.
        yield self.create_json_message({"results": results})
        yield self.create_text_message(_format_results(query, results))


def _result_snippet(result: dict[str, Any]) -> str:
    """Pick a result's text for the digest.

    Keenable returns both ``snippet`` and ``description``: ``snippet`` carries
    the page text and ``description`` is frequently empty, so prefer whichever
    has content. Snippets are raw page text with newlines in them, which would
    break the digest's one-line-per-field layout, and Keenable returns whole
    pages where other engines return a short snippet — hence the collapse and
    the cap. The untouched results still go out via ``create_json_message``.
    """
    text = " ".join(str(result.get("snippet") or result.get("description") or "").split())
    return text[:MAX_SNIPPET_CHARS]


def _format_results(query: str, results: list[dict[str, Any]]) -> str:
    lines = [f"Search results for {query!r}:", ""]
    for i, result in enumerate(results, start=1):
        title = result.get("title") or result.get("url") or "(untitled)"
        url = result.get("url") or ""
        snippet = _result_snippet(result)
        published = result.get("published_at")
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   {url}")
        if published:
            lines.append(f"   published: {published}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()
