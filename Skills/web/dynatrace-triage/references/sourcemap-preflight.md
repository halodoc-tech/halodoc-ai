# Sourcemap Preflight (Generic)

Run once per heal run, before the batch loop (Phase 0). Purpose: ensure the
target web project generates production sourcemaps so minified stack traces
can be symbolicated — for this run (via the existing S3 workflow in
[sourcemaps.md](./sourcemaps.md)) and for all future runs.

This preflight is framework-agnostic — it must work for any web project, not
just Angular.

## Detection (first match wins)

Check the target repo root for the framework config and its production
sourcemap setting:

| Framework | File | Enabled when |
|---|---|---|
| Angular | `angular.json` (or `project.json`) | production configuration has truthy `sourceMap` — preferred shape `{"scripts": true, "hidden": true}` |
| Next.js | `next.config.{js,mjs,ts}` | `productionBrowserSourceMaps: true` |
| Vite | `vite.config.{js,ts,mjs,mts}` | `build.sourcemap` is `true` or `'hidden'` |
| Webpack | `webpack.config.*` / `webpack.prod.*` | production `devtool` includes `source-map` (prefer `hidden-source-map`) |

Notes:

- For Angular, inspect the **production** configuration specifically
  (`projects.<name>.architect.build.configurations.production`), falling back
  to the builder's base `options` when production doesn't override it.
- If your project already has hidden sourcemaps enabled (e.g. Angular's
  `"sourceMap": {"scripts": true, "hidden": true}`), the preflight is a
  **no-op**.

## Decision table

| State | Action |
|---|---|
| Sourcemaps enabled | Log `preflight: sourcemaps already enabled (no-op)`, record `already-enabled` in the registry (`registry.py preflight --result already-enabled`), continue. |
| Disabled / absent | Apply the **smallest config edit**, preferring hidden sourcemaps (maps generated, not referenced from the served JS). Commit on a dedicated branch `chore/enable-prod-sourcemaps`, push, open its own MR with the auto-heal marker/labels. Record `enabled-in-mr <url>` and continue the run. |
| Config unreadable / unknown framework | Do NOT guess. Record `failed: <why>`, surface as a blocker in the run report, continue the run (symbolication falls back per sourcemaps.md). |

Rules:

- The sourcemap enablement change goes on its **own branch/MR** — never mixed
  into an error-fix branch.
- Prefer hidden sourcemaps for security: browsers must not be pointed at the
  maps; only the deploy pipeline / monitoring tooling consumes them.

## Scope note

The preflight controls **future** symbolication quality. Deobfuscation for the
current run still uses whatever maps already exist for the deployed build —
see [sourcemaps.md](./sourcemaps.md) for where those live and how to fetch
them. If the deployed build predates sourcemap enablement, say so explicitly
and fall back to the non-sourcemap signals.
