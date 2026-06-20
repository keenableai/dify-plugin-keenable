# Keenable for Dify

Web search and page fetch built for AI agents, as a Dify **tool** plugin.
**Keyless by default** — it works with no signup or API key; add a key later to
raise rate limits and unlock realtime search.

Two tools:

- **Keenable Search** — search the web and get ranked results (title, URL,
  snippet, publication date), with optional `site` and date filters and a
  `pro` / `realtime` mode.
- **Keenable Fetch** — read a single web page and get its main content as clean
  markdown, with navigation and boilerplate stripped.

## Setup

1. Install the plugin from the Dify Marketplace (or upload the `.difypkg`).
2. **Authorize** the provider. The API key field is **optional**:
   - Leave it empty to use Keenable keyless (free tier).
   - Paste a key (`keen_...`) to raise rate limits and enable `realtime` mode.
     Create one at <https://keenable.ai>.
3. Add **Keenable Search** / **Keenable Fetch** to an Agent or a Workflow tool
   node.

## Usage

In an **Agent app**, the model calls the tools itself: it searches, then fetches
the most relevant result to read the full page.

In a **Workflow**, add a Tool node:

- *Keenable Search* — set `query` (and optionally `mode`, `site`,
  `published_after`, `published_before`). Outputs `json` (`{"results": [...]}`)
  and a formatted `text` digest.
- *Keenable Fetch* — set `url`. Outputs the page as `json` (with `content` and
  metadata) and as `text` (the markdown content).

## Tool reference

### Keenable Search

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | The search query. |
| `mode` | select (`pro` / `realtime`) | no | `pro` (default, deeper) or `realtime` (low latency, needs a key). |
| `site` | string | no | Restrict results to a single domain, e.g. `github.com`. |
| `published_after` | string | no | Only pages published on/after `YYYY-MM-DD`. |
| `published_before` | string | no | Only pages published on/before `YYYY-MM-DD`. |

### Keenable Fetch

| Parameter | Type | Required | Description |
|---|---|---|---|
| `url` | string | yes | Absolute `http(s)` URL to fetch and read. |

## Privacy

Queries, fetched URLs, and any provided API key are sent to the Keenable API
(`https://api.keenable.ai`) to fulfill each request. See [PRIVACY.md](./PRIVACY.md).

## Source & support

- Source repository: <https://github.com/keenableai/dify-plugin-keenable>
- Keenable: <https://keenable.ai> · support@keenable.ai
