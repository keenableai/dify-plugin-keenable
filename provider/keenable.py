from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.keenable_client import KeenableError, keenable_post, resolve_api_key


class KeenableProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate the (optional) Keenable API key.

        Keenable is keyless by default, so an empty key is valid: there is
        nothing to authenticate and the public endpoints are used. When a key is
        supplied we probe the authenticated search endpoint so an invalid key is
        rejected here rather than surfacing on first use.
        """
        api_key = resolve_api_key(credentials.get("keenable_api_key"))
        if not api_key:
            return
        try:
            keenable_post(
                "/v1/search/public",
                "/v1/search",
                {"query": "keenable", "mode": "pro"},
                api_key,
                timeout=15.0,
            )
        except KeenableError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
