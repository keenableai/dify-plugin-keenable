from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils.keenable_client import (
    KeenableError,
    keenable_get,
    reject_private_fetch_target,
    resolve_api_key,
)


class KeenableFetchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        url = (tool_parameters.get("url") or "").strip()
        if not url:
            yield self.create_text_message("Please provide a URL to fetch.")
            return
        if not url.lower().startswith(("http://", "https://")):
            yield self.create_text_message(f"Refusing to fetch a non-http(s) URL: {url!r}")
            return
        try:
            reject_private_fetch_target(url)
        except KeenableError as e:
            yield self.create_text_message(str(e))
            return

        api_key = resolve_api_key(self.runtime.credentials.get("keenable_api_key"))
        try:
            data = keenable_get(
                "/v1/fetch/public", "/v1/fetch", {"url": url}, api_key, timeout=30.0
            )
        except KeenableError as e:
            yield self.create_text_message(str(e))
            return

        content = data.get("content") or ""
        yield self.create_json_message(data)
        if content:
            yield self.create_text_message(content)
        else:
            yield self.create_text_message(f"No readable content returned for {url!r}.")
