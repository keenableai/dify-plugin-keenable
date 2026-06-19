# Privacy Policy — Keenable plugin for Dify

This plugin connects Dify to the Keenable web-search API (`https://api.keenable.ai`).

## What data is sent

- **Keenable Search** sends your search query and any optional filters you set
  (mode, site, date range) to the Keenable API.
- **Keenable Fetch** sends the URL you ask to read to the Keenable API.
- An optional API key, if you provide one in the plugin credentials, is sent as
  the `X-API-Key` request header to authenticate and raise rate limits. With no
  key the plugin uses Keenable's keyless public endpoints.
- Each request carries a `User-Agent` (`keenable-dify/<version>`) and an
  `X-Keenable-Title: Dify` header so Keenable can attribute traffic from this
  integration. No personal data is included in these headers.

The plugin does not collect, store, or transmit any data beyond what is required
to fulfill each search or fetch request. It keeps no logs of its own.

## Third-party processing

Queries, URLs, and any provided API key are sent to and processed by Keenable
(<https://keenable.ai>) to return search results and page content for the
request that included them. Server-side handling and retention of those requests
are governed by Keenable's terms; contact Keenable at the address below for
details.

## Contact

Questions about this plugin's data handling: support@keenable.ai
