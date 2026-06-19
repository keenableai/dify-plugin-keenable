# Publishing the Keenable Dify plugin

## Prerequisites

- Python ≥ 3.12.
- The Dify CLI (`dify-plugin-daemon`):
  `brew tap langgenius/dify && brew install dify`, or download the
  `dify-plugin-<os>-<arch>` binary from
  [langgenius/dify-plugin-daemon releases](https://github.com/langgenius/dify-plugin-daemon/releases).

## 1. Local test

```sh
uv venv .venv -p 3.12
uv pip install --python .venv/bin/python "dify_plugin>=0.9.0,<0.10.0" requests pytest ruff
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check .
```

## 2. Remote debug (optional, recommended before submitting)

In Dify → **Plugins → Debug**, copy the remote server address + debugging key
into `.env` (from `.env.example`), then:

```sh
.venv/bin/python -m main
```

The plugin installs live into your Workspace. Authorize it with **no key**
(keyless), add **Keenable Search** / **Keenable Fetch** to an Agent, and confirm
both tools run. Then re-authorize with a real `keen_...` key and confirm the
authenticated path.

## 3. Package

```sh
dify plugin package . -o keenable.difypkg
```

Validates the manifest + structure and produces `keenable.difypkg`
(`.venv`/`tests`/caches are excluded by `.difyignore`).

## 4. Submit to the Marketplace

1. Push the source to the canonical repo `keenableai/dify-plugin-keenable`.
2. Fork [`langgenius/dify-plugins`](https://github.com/langgenius/dify-plugins).
3. Add the plugin under `keenable/keenable/` — the **source files and the built
   `keenable.difypkg`**.
4. Open a PR using the repo's PR template. Address review comments within 14
   days (stale) / 30 days (auto-closed).
5. On merge, the plugin is auto-listed on the Dify Marketplace.

### Auto-PR (optional, for later releases)

Add `.github/workflows/plugin-publish.yml` + a `PLUGIN_ACTION` PAT secret to the
canonical repo. On push to `main` it reads `manifest.yaml` (`name`, `version`,
`author`), packages the `.difypkg`, pushes to your `dify-plugins` fork on
`bump-keenable-plugin-<version>`, and opens the upstream PR. **Bump
`manifest.yaml version` and `PLUGIN_VERSION` in `utils/keenable_client.py`
together on every release.**
