---
name: gsc-driven-prerendering
version: "1.0.0"
maintainer: "halodoc-ai"
description: >
  Angular 17+ / @angular/ssr: Set up or extend Google Search Console-driven prerendering — generate
  a typed click-ranked params list and wire it into ServerRoute getPrerenderParams. Triggers on:
  "prerender Angular routes from SEO traffic", "set up GSC prerender", "configure prerendering from
  Search Console", "add prerender route from clicks", "click-based prerendering",
  "automate Angular prerender with GSC", "GSC prerender skill",
  "prerender most visited Angular pages", "use search traffic to pick prerender routes",
  "rank prerender routes by SEO clicks", "getPrerenderParams from analytics".
when_to_use: >
  Use when the user wants to drive Angular SSR prerendering from real search traffic or SEO data —
  e.g. "prerender the most visited pages", "use Google Search Console to pick routes to prerender",
  "replace hardcoded prerender params with real traffic data", "set up GSC-driven Angular prerender",
  "automate prerender route list from analytics", "rank Angular SSR routes by SEO clicks".
  Requires Angular 17+ with @angular/ssr and RenderMode.Prerender.
---

# GSC-Driven Prerendering

This skill helps you replace hardcoded prerender route lists with one driven by real Google Search Console click data.

> **Prerequisites:** Angular 17+ with `@angular/ssr` installed and `RenderMode.Prerender` in use.
> **Node.js 18+** required (`node --version` to confirm — 14.8+ works only with `--experimental-vm-modules`).
> If your app uses `@nguniversal` or an older Angular SSR approach, this skill does not apply.

The pattern:

1. A Node script queries GSC once per dynamic route, sorts pages by clicks, and emits a typed TS constants file.
2. `app.routes.server.ts` references that constants file from `getPrerenderParams` for each `RenderMode.Prerender` route.
3. The script runs on a schedule (CI/CD pipeline, cron, etc.) and opens an MR/PR when results shift. **Scheduling and MR automation are out of scope for this skill** — stop at script + routes wiring.

---

## Step 1: Decide which flow you need

| Situation | Flow |
|---|---|
| No `scripts/run-gsc-prerender.*` exists in the project | **Bootstrap** (Step 2) |
| Script exists, you want to add a new dynamic route to it | **Extend** (Step 3) |
| Script exists, you want to retune limits / regex / prefix | **Extend** (Step 3, edit-in-place subset) |

If unsure, run:

```bash
ls scripts/run-gsc-prerender.* 2>/dev/null
grep -r "gscPrerenderParamsData" src/ 2>/dev/null
```

Both empty → Bootstrap. Either non-empty → Extend.

---

## Step 2: Bootstrap (first-time setup)

Bootstrap creates or modifies exactly these files:

| File | Action |
|---|---|
| `scripts/run-gsc-prerender.mjs` | Created from template — edit the four marked sections |
| `package.json` | Modified — add `gsc-prerender` script |
| `src/app/utils/gsc-prerender-params.ts` | Created — typed `GscPrerenderParams` interface |
| `src/app/app.routes.server.ts` | Modified — add `ServerRoute` entries with `getPrerenderParams` |
| `src/app/prerender-routes/gsc-prerender-params.constant.ts` | **Generated** — committed after the first `npm run gsc-prerender` run |

### 2.1 Confirm the project is an Angular SSR app

The pattern depends on `@angular/ssr`'s `ServerRoute.getPrerenderParams`. Verify:

```bash
grep -E "RenderMode|@angular/ssr" src/app/app.routes.server.ts
cat angular.json | grep -i ssr
```

If the app isn't using `@angular/ssr` with `RenderMode.Prerender`, stop and flag it to the user — this skill assumes that foundation.

### 2.2 Install the GSC client

```bash
npm install googleapis
# or: pnpm add googleapis / yarn add googleapis
```

Confirm `node --version` ≥ 18 (see prerequisites above).

The script uses `google.searchconsole({ version: 'v1' })`. No other runtime deps are needed.

### 2.3 Drop in the runner script

The template script is bundled at `scripts/run-gsc-prerender.template.mjs` in this skill.

```bash
# If using Claude Code (skill is installed locally):
cp <skill-dir>/scripts/run-gsc-prerender.template.mjs scripts/run-gsc-prerender.mjs

# If setting up manually: copy the full contents of
# scripts/run-gsc-prerender.template.mjs from this skill's repository
# into scripts/run-gsc-prerender.mjs in your project.
```

> **For Claude Code:** Read `scripts/run-gsc-prerender.template.mjs` from this skill's
> directory (bundled alongside this SKILL.md) and write its full contents to
> `scripts/run-gsc-prerender.mjs` in the user's project. Do not modify the template
> contents — the user edits the four marked sections after it is placed.

Then edit the four marked sections in the script:

1. **`GSC_SITE_URL`** — the verified GSC property (must match host/protocol exactly, e.g. `https://www.example.com`).
2. **`OUTPUT_FILE`** — keep at `src/app/prerender-routes/gsc-prerender-params.constant.ts` unless the project has a different convention. The header comment marks it as generated.
3. **`MAX_PRERENDER`** — start each path at `10`. Tune later (see [path-query-recipe.md](references/path-query-recipe.md)).
4. **`PATH_QUERIES`** — one entry per dynamic Angular route. See Step 3.2 for how to compose each entry.

The script writes a header comment marking the output as generated. Don't strip it — reviewers rely on it.

### 2.4 Add the npm script

In `package.json`:

```json
{
  "scripts": {
    "gsc-prerender": "node scripts/run-gsc-prerender.mjs"
  }
}
```

### 2.5 Create the typed companion

Create `src/app/utils/gsc-prerender-params.ts` with the interface, mirroring the keys you'll add to `PATH_QUERIES`:

```ts
/**
 * Types and documentation for GSC-driven prerender params.
 * Actual data is generated by: npm run gsc-prerender
 * Output: src/app/prerender-routes/gsc-prerender-params.constant.ts
 */
export interface GscPrerenderParams {
  // one entry per PATH_QUERIES name. Example:
  // articles: { slug: string }[];
}
```

This type isn't imported by `app.routes.server.ts` directly (the constants are inferred), but it documents the contract and is useful for tests.

### 2.6 Wire `getPrerenderParams` in `app.routes.server.ts`

For each dynamic route you added to `PATH_QUERIES`, add a matching `ServerRoute`:

```ts
import { RenderMode, ServerRoute } from '@angular/ssr';
import { gscPrerenderParamsData } from './prerender-routes/gsc-prerender-params.constant';

export const serverRoutes: ServerRoute[] = [
  {
    path: 'articles/:slug',
    renderMode: RenderMode.Prerender,
    getPrerenderParams: async () => gscPrerenderParamsData.articles,
  },
  // ... one entry per PATH_QUERIES name ...
];
```

**Three things must align:**

- `path`'s `:param` name → `PATH_QUERIES[i].paramKey`
- `gscPrerenderParamsData.<key>` → `PATH_QUERIES[i].name`
- `prefix` in `PATH_QUERIES[i]` → matches the static segment(s) of `path`

A mismatch is silent — the build succeeds but the route isn't actually prerendered.

**Verify alignment before committing:**
```bash
# paramKey in PATH_QUERIES must match the Angular route's :param name
grep -E "path:.*'" src/app/app.routes.server.ts
grep "paramKey" scripts/run-gsc-prerender.mjs

# gscPrerenderParamsData key must match the PATH_QUERIES name
grep "gscPrerenderParamsData\." src/app/app.routes.server.ts
grep "  name:" scripts/run-gsc-prerender.mjs
```
All three must reference the same string. A mismatch produces no build error — the route is silently skipped.

### 2.7 Service account credential

The script needs a GSC service account JSON key at `$GSC_KEY_DIR/gsc-service-account.json`. Walk through [references/service-account-setup.md](references/service-account-setup.md) once per project. Confirm the smoke test in §5 of that doc passes before going further.

### 2.8 First run + commit the generated file

```bash
GSC_KEY_DIR=/path/to/key/dir npm run gsc-prerender
```

The script logs the output path and the JSON it wrote. Sanity-check the JSON (see "Sanity-checking" in [path-query-recipe.md](references/path-query-recipe.md)). Commit the generated `gsc-prerender-params.constant.ts` so builds without GSC access still work — the script regenerates it on the schedule.

> **New site or path with no recent traffic?** The script queries the last 7 days. Note that GSC
> has a 2–3 day processing delay, so very recent traffic may not appear immediately. If a path has
> no clicks in that window, the output will be an empty array — this is expected. Manually seed
> the constants file with known slugs for the initial commit, then let the weekly script run take
> over once traffic data is available.

### 2.9 Hand off

Tell the user:

- The script is wired and the first generation is committed.
- They (or their platform team) need to schedule `npm run gsc-prerender` to run **weekly** and open an MR/PR with the regenerated file — weekly matches the 7-day query window. **This skill does not configure that scheduling.**
- The service-account key needs to exist in the CI environment with `GSC_KEY_DIR` exported.

---

## Step 3: Extend (add or retune a path)

### 3.1 Locate the four files

Every change touches exactly these four:

| File | Purpose |
|---|---|
| `scripts/run-gsc-prerender.mjs` | `PATH_QUERIES` + `MAX_PRERENDER` |
| `src/app/utils/gsc-prerender-params.ts` | `GscPrerenderParams` interface |
| `src/app/app.routes.server.ts` | matching `ServerRoute` with `getPrerenderParams` |
| `src/app/prerender-routes/gsc-prerender-params.constant.ts` | **generated** — regenerated by the script; commit the updated output |

Do not hand-edit the generated constants file — let the script produce it.

### 3.2 Compose the new `PATH_QUERIES` entry

Read [path-query-recipe.md](references/path-query-recipe.md) before writing the entry. Key checks:

- `regex` is RE2 (no lookahead). Anchor with `^`. Use `[^/]+` for a single segment.
- `paramKey` matches the `:param` in the Angular route exactly.
- `prefix` starts and ends with `/`.
- If two paths overlap (e.g. `/foo/:slug` and `/foo/category/:slug`), use `filterRow` on the broader one and add a dedicated entry for the narrower one.

Add the new key to `MAX_PRERENDER` (start at `10`) and to `PATH_QUERIES`.

### 3.3 Update the interface

Add the matching member to `GscPrerenderParams` in `src/app/utils/gsc-prerender-params.ts`:

```ts
export interface GscPrerenderParams {
  // existing entries...
  newPath: { slug: string }[];   // paramKey must match PATH_QUERIES entry
}
```

### 3.4 Add the `ServerRoute` entry

```ts
{
  path: 'new-path/:slug',
  renderMode: RenderMode.Prerender,
  getPrerenderParams: async () => gscPrerenderParamsData.newPath,
},
```

**Verify alignment before committing:**
```bash
# paramKey in PATH_QUERIES must match the Angular route's :param name
grep -E "path:.*'" src/app/app.routes.server.ts
grep "paramKey" scripts/run-gsc-prerender.mjs

# gscPrerenderParamsData key must match the PATH_QUERIES name
grep "gscPrerenderParamsData\." src/app/app.routes.server.ts
grep "  name:" scripts/run-gsc-prerender.mjs
```
All three must reference the same string. A mismatch produces no build error — the route is silently skipped.

### 3.5 Regenerate locally and verify

```bash
GSC_KEY_DIR=/path/to/key/dir npm run gsc-prerender
```

Open the regenerated `gsc-prerender-params.constant.ts` and check the new key is present, populated, and the values look right. If the list is empty:

- Spot-check the regex against actual URLs in GSC's "Performance" report.
- Confirm the GSC property has traffic on those URLs in the last 7 days.
- Confirm `prefix` matches the actual pathname.

### 3.6 Commit all four files together

The runner script change, interface, server route, and the regenerated constants file go in the **same commit/MR** so reviewers can verify the data shape lines up with the route wiring.

---

## Pitfalls (read before debugging)

| Symptom | Likely cause |
|---|---|
| Build succeeds but new route isn't prerendered | `paramKey` doesn't match the Angular route's `:param`, or the `ServerRoute` path is wrong |
| `npm run gsc-prerender` writes empty arrays | Service account lacks GSC permission on the property, or regex/prefix mismatch — see [service-account-setup.md](references/service-account-setup.md) §"Common errors" |
| Build time exploded after a change | A `MAX_PRERENDER` was bumped too high, or a regex now captures nested paths — sanity-check the JSON dump |
| Generated file has values with `/` or `?` in them | Regex too broad or prefix wrong — tighten in [path-query-recipe.md](references/path-query-recipe.md) terms |
| Two `ServerRoute` entries fight (e.g. `/foo/:slug` matching `/foo/category/x`) | Need a `filterRow` on the broader query plus a dedicated narrower entry |
| `403 SERVICE_DISABLED` | Search Console API not enabled in the GCP project |
| Property not visible to the service account | `GSC_SITE_URL` host/protocol doesn't match what's verified in GSC, or the service account email wasn't added in **Settings → Users and permissions** |

---

## What this skill does not cover

- **Scheduling** the script (GitHub Actions, GitLab CI, Jenkins, cron). The user's platform team owns this.
- **Auto-MR/PR creation** when the regenerated file diffs.
- **Notifications** (Slack, Teams, etc.) on schedule completion.
- **GSC property verification** itself — the property must already be verified before the service account can read it.
- **Tuning the click threshold strategy** beyond the per-path `MAX_PRERENDER`. Tuning is a product/SEO decision, not a code change.
