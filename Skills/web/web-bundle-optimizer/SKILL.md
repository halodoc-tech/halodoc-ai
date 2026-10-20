---
name: web-bundle-optimizer
description: >
  Measures and reduces the first-load JavaScript bundle of an Angular web repo built with
  `@angular/build` (esbuild), including SSR, zoneless and Native Federation apps. Builds with
  `--stats-json`, walks the esbuild metafile to separate the EAGER set (what the browser
  downloads before any lazy route) from lazy chunks, attributes every eager byte to an npm package
  and then to the internal shared repo that owns it (`@design-system`, `@web-shared`, `@your-org`), ranks
  reduction candidates from a pattern playbook, applies them one at a time, re-measures, ratchets
  the `initial` budget in angular.json so the win cannot regress, and raises a merge/pull request with a
  before/after table. Trigger: "reduce the bundle size", "analyze the bundle", "why is our main
  bundle so big", "bundle analysis", "shrink initial load", "what's in main.js", "add a bundle
  budget", "bundle regression", "how much does <package> cost us", "which shared library is making
  us heavy", "is our design system bloating our bundle", "analyze the dependencies". NOT
  runtime/Core-Web-Vitals profiling, NOT Angular version bumps (`angular-upgrade`), NOT
  code-quality migrations.
---

# Web Bundle Optimizer

## Core Directive

**Detect → Baseline → Attribute (package, then owning repo) → Rank → Apply ONE → Re-measure →
Ratchet budget → Repeat → MR.**

Every claim in the final report is a measured delta between two metafiles. This skill never
reports an estimate as a result. Estimates exist only to *rank* candidates before they are tried.

> **Safety contract:** one candidate per commit; after each candidate the repo must still pass
> `<BUILD_CMD>` + `<TEST_CMD>` + `<LINT_CMD>` (Step 1 detects the real commands — never assume
> `pnpm`). A candidate that fails any of them, or that does not produce the predicted movement in
> the metafile, is reverted with `git revert`/`git restore` and demoted to the REPORT tier. The
> branch is never left broken and a "saving" is never claimed without a metafile proving it.

## Out of Scope

Runtime performance (LCP/INP/CLS, Lighthouse, k6). Angular version bumps → `angular-upgrade`.
Deprecation/API migrations. Webpack-builder repos:
this skill's analyzer reads esbuild metafiles only — Step 1 detects the builder and stops with a
clear message rather than producing wrong numbers.

## Step 0 — Guard

Confirm the working directory is an Angular web repo: `angular.json` (or `workspace.json`) exists
AND `package.json` has `@angular/core`. If not, stop and say so. Do not "adapt" to a React or
Node repo.

## Step 1 — Detect the toolchain

Read, do not assume:

| What | Where | Why it matters |
| --- | --- | --- |
| Builder | `angular.json` → `projects.*.architect.build.builder` | `@angular/build:application` / `@angular-devkit/build-angular:application` = esbuild = supported. `:browser` / webpack = **stop**. |
| Package manager | lockfile (`pnpm-lock.yaml` / `package-lock.json` / `yarn.lock`) | every command below |
| Build/test/lint scripts | `package.json` → `scripts` | `<BUILD_CMD>`, `<TEST_CMD>`, `<LINT_CMD>` |
| Prod configuration name | `angular.json` → `configurations` | usually `production`; some repos also have `preprod`, `staging` |
| Existing budgets | `angular.json` → `configurations.production.budgets` | the ratchet target in Step 6 |
| SSR | `ssr` / `outputMode` / `server` keys | affects where `stats.json` lands and whether a change can break hydration |

Record all of it in the report header. `references/detection.md` has the exact lookups and the
fallbacks for older Angular layouts.

## Step 2 — Baseline

```bash
<BUILD_CMD> --configuration=<PROD_CONFIG> --stats-json
node <SKILL_DIR>/scripts/analyze-bundle.mjs --out bundle-baseline.json --md bundle-baseline.md
```

`<SKILL_DIR>` is this skill's own directory — the one holding this SKILL.md. Its `scripts/`
are dependency-free Node ESM and run straight from there; Step 7 copies them into the repo.

`analyze-bundle.mjs` auto-discovers `dist/browser/stats.json` (or `dist/stats.json`). It walks
`outputs[*].imports`, ignoring every `dynamic-import` edge, so the eager set is derived from the
real module graph rather than from filename guessing.

Commit `bundle-baseline.json` to the branch. Every later number is relative to this file, and a
reviewer must be able to reproduce it.

**Report these three numbers, always, and never collapse them into one:**

- `main-*.js` raw and gzip — the literal "main bundle" the OKR usually names.
- **eager JS raw and gzip** — every chunk reachable without a dynamic import. This is what the
  user actually waits for, and it is the honest metric.
- total JS emitted — context only. It goes *up* when you lazy-load something, which is correct.

If a stakeholder metric is stated as "main bundle", report the `main-*.js` line as the headline
and the eager line immediately beneath it. Do not silently substitute one for the other.

## Step 3 — Attribute and rank

`baseline.md` contains a per-package table of the eager set. For each of the top packages, decide
which playbook pattern applies. `references/playbook.md` is the catalog; each entry has a
detection query, an estimated saving, a risk level, and the verification that proves it landed.

The highest-yield patterns, in the order they usually pay off:

1. **Eager side-effect registration in `main.ts`** — a `register()` / `defineCustomElements()` /
   polyfill shim imported at bootstrap for a library only a handful of lazy routes use.
2. **Eager `importProvidersFrom` in the app config** — `forRoot()` modules pulled in for features
   that are route-scoped.
3. **Static imports of feature internals from the root routes file** — guards, resolvers, services
   and i18n loader factories imported at the top of `root-routes.ts` drag their whole module graph
   into the eager set even though the route itself is `loadComponent`/`loadChildren`.
4. **Always-on shell UI** — footer, mega-menu, modals, banners rendered by the root component.
   `@defer (on viewport)` / `(on interaction)`.
5. **Barrel / entry-point hygiene** — `@angular/material`, date and crypto libraries.

Present the ranked list to the developer as a numbered menu with estimated saving, effort and
risk, and let them choose. Do not apply everything you found.

## Step 3.5 — Attribute the eager set to the repo that owns it

Package-level attribution is not enough to plan the work. In a typical org most of a web app's eager set
belongs to internal libraries published from a few shared repos, and a large share of the plausible
fixes are not in the app being optimized at all. Run this **before** choosing candidates:

```bash
node <SKILL_DIR>/scripts/analyze-deps.mjs \
  --report bundle-report.json --repos-root .. \
  --scopes @design-system,@web-shared,@your-org --owner-hosts git.example.com --md bundle-deps.md
```

`@design-system,@web-shared,@your-org` and `git.example.com` are placeholders. Replace them with
the repo's own internal npm scopes (the private scopes in `package.json` → `dependencies`, or the
scopes in `.npmrc` registry lines) and its git host. With neither flag the script attributes nothing
to internal repos and says so — it does not guess.

`--scopes` is a seed, not the whole rule. A package also counts as **ours** when its installed
manifest's `repository`/`homepage` points at one of `--owner-hosts`, which is what catches unscoped names
(`design-system`, `web-shared`) and any scope nobody remembered to pass.

**Packaging verdicts and fix lists are produced for owned packages only.** For a package we do not
publish there is no packaging finding to raise — we cannot set its `sideEffects`, split its entry
points, or "fix its bundling", and forking it to move a number is not a fix. Those packages stay in
the report as context, under the table of who requires them, where the only honest lever is
deferring *our* importer.

It reads `package.json`, resolves each owned package to its installed output *and* to its local
source repo, and produces five tables. **The first one is the answer to "where do I get the KB":**

- **a ranked plan, simulated on the module graph** — each row is one concrete edit (a static import
  that becomes dynamic, a template usage that becomes `@defer`, a bootstrap provider that moves to
  route-level `providers`), with the KB that *actually* leave the eager set when those exact import
  edges are cut and reachability is recomputed, plus the eager total **before and after** that row
  and a before/after summary in raw and gzip. `Cumulative` re-simulates with the earlier rows
  applied, so two edits freeing the same shared chunk are counted once. The app shell (`main.ts`,
  `app.config.ts`, `app.component.ts`) is never a row — it cannot be lazy, only its imports can.
  Rows span both repos: an edge whose source is app code is this repo's MR, an edge whose source is
  an internal library (`@design-system/atoms` -> `@angular/material`) is that library's MR, and the `Repo`
  column says which. Source packages are filtered to ones your org owns — a third-party importing
  another third-party is not a row, because there is no MR to send. **Barrel-split rows are
  appended as estimates**, apportioning a barrel's eager bytes by how many of its exports the eager
  importers actually name: the only available number for the lever that changes bytes rather than
  reachability, and never folded into the simulated before/after total.
- **what no app-side edit can free** — packages where cutting *every* app import frees under 20 KB,
  because library-to-library edges keep them reachable. Sum this before promising a percentage:
  on the reference app (a large Angular SSR site) the app-side plan is 320 KB (12.9% of eager) and 1552 KB is
  upstream work. Lead the report with both numbers.

Then, for planning the upstream half:

- **eager bytes per owning repo** — the "bigger picture" number. One shared repo commonly owns
  30–40% of first load, which reframes the work from "our app is heavy" to "our design system is
  eagerly rendered by our shell".
- **packaging verdict per library** — `upstream` when a concrete defect blocks the bundler
  (`sideEffects` not `false`, NgModules in the published output, a heavy hard dependency, or a
  **failed shake probe**), `consumer` otherwise.
- **shake probe** — the verdict that outranks the rest, because it is measured rather than
  inferred: the script bundles one non-component symbol and then the whole barrel with the repo's
  own esbuild. One symbol costing ~the whole barrel means the entry point is indivisible, so
  `sideEffects: false` is decorative and secondary entry points are the fix. Every eager internal
  library on the reference app (a large Angular SSR site) failed it at 90–100% retained — one string constant from
  `@design-system/atoms` costs 260 KB. A probe that cannot run reports `not measured`, never a pass.
- **how to fix each owned dependency** — one block per package above 20 KB, each item naming what
  to change, the *actual* importers read off the metafile (app files, plus the libraries that also
  hold it eager, which mark the item **blocked**), why those bytes are there, and the command that
  proves the change landed. This is the section a developer works from; hand it over as-is rather
  than summarising it. Pass `--dist` so the importers can be resolved — without a metafile the
  items degrade to naming the pattern only.
- **third-party packages we do not own** — context only, including `peerDependencies`: no packaging
  verdict, just the importer that decides when they load.

Three rules follow from it, and they decide the plan:

1. **Do not "fix" a correctly packaged library — but prove it is correctly packaged.** A single
   entry point is not a defect *when tree-shaking actually works*: esbuild drops unused symbols
   from a flat FESM, so deep-path imports would change nothing. Read that verdict off the shake
   probe, not off `sideEffects: false`, which the internal libraries all set while shaking nothing.
   When the probe fails, secondary entry points are the fix and the refactor is justified.
2. **A dependency several internal libraries require cannot be dropped by the app.** If five
   libraries require `@angular/material`, local import hygiene will not remove it while those
   libraries are eager. Defer the *library's* usage first; the third-party package follows.
3. **A packaging defect in a package we do not own is not a finding.** Report it as a size fact if
   it matters, never as work — the actionable line for a third-party package is always deferring
   the code that imports it, or replacing it.
4. **Upstream findings are another repo's MR.** Report them with the eager bytes and the exact
   packaging fact, raise them on the owning repo, and state in the report that they are outside
   this MR. Never patch `node_modules`, never pin a fork to make a number move.

`references/internal-libraries.md` has the signal table, the retained-% caveat, and how to turn
each verdict into work.

### Mandatory before any defer candidate: trace the last eager importer

```bash
node <SKILL_DIR>/scripts/analyze-deps.mjs --trace @design-system/atoms --dist dist
```

A chunk leaves the eager set only when its **last** eager importer does, and eager importers are
usually not all in app code. Grepping `src/` finds the two components you can defer and hides the
seven libraries that also import the package — defer the two, and the chunk stays exactly where it
was. `--trace` lists both groups from the metafile and states plainly whether the candidate can
work.

Run it for the package a candidate is supposed to remove. If any library importer is listed, either
widen the candidate to cover them or pick a different package. Do not spend a build proving what
the trace already ruled out.

## Step 4 — Apply ONE candidate

One candidate, one commit. Follow the pattern's recipe in `references/playbook.md`.

Non-negotiable for SSR repos: a change must not alter server-rendered markup, or hydration breaks.
Deferring *work* is safe; deferring *DOM* requires `@defer` with a matching `@placeholder`, and
must be verified by diffing the SSR HTML before and after.

## Step 5 — Re-measure and prove it

```bash
<BUILD_CMD> --configuration=<PROD_CONFIG> --stats-json
node <SKILL_DIR>/scripts/analyze-bundle.mjs --out bundle-report.json --md bundle-report.md
node <SKILL_DIR>/scripts/compare-bundle.mjs \
  --baseline bundle-baseline.json --current bundle-report.json --md bundle-delta.md \
  --goal <STAKEHOLDER_TARGET_PCT> --metric eager-gzip
```

`bundle-delta.md` carries four sections, and the report must reproduce all four —
before/after table, packages that moved, **Verdict**, **What to improve next**:

- **Verdict** states whether this was a real first-load saving or bytes merely relocated out of
  `main` into another eagerly-imported chunk. A large `main` drop with a flat eager total is a
  relocation and must not be reported as a saving. It also separates packages that *left* the
  eager set from ones that only *shrank* — the latter means an eager importer was missed.
- **Against the goal** (`--goal`) prints how many KB still have to go to reach the stated target.
- **What to improve next** ranks the packages still in the eager set, each tagged with the
  playbook pattern that applies. This is the input to the next candidate and to the conclusion of
  the report. Framework packages are excluded — they are the floor, not an opportunity.

Then run `<TEST_CMD>` and `<LINT_CMD>`.

Three gates, all mandatory:

- the metafile shows the package leaving the eager set (check the "packages that moved" table —
  a package that merely *shrank* usually means the change was partial);
- tests and lint pass;
- for SSR repos, the rendered HTML of an affected route is unchanged:
  ```bash
  # before the change, on the base commit, and again after — then diff the two
  <SERVE_SSR_CMD> &                       # e.g. `pnpm run serve:ssr:prod`
  curl -s http://localhost:4000/<route> > /tmp/ssr-<label>.html
  diff /tmp/ssr-before.html /tmp/ssr-after.html
  ```
  Markup that differs means hydration is at risk. Deferring *work* should produce no diff;
  only a deliberate `@defer` of DOM (pattern P4) may, and then the placeholder must account
  for every changed line.

  SSR edge cases, in order of what to try:
  - **no `serve:ssr:prod` script** — look for `serve:ssr` / `dev:ssr` in `package.json`, else run
    Angular's SSR entry directly: `node dist/server/server.mjs` (older layouts:
    `dist/<project>/server/server.mjs`). A non-prod SSR build is fine for this check — it detects
    markup change, not speed.
  - **route behind auth** — diff a public route that renders the changed component instead
    (`/`, `/id/home`, a product or article page). Never disable the guard to make the check pass.
  - **no route renders the change server-side at all** (change is inside a lazy route or a
    browser-only code path) — say so in the report and skip the diff; do not record it as passed.

Any gate failing ⇒ revert the candidate, record it in the REPORT tier with the reason, move on.

`compare-bundle.mjs --min-reduction <pct> --metric main|eager-gzip|eager-raw` exits 2 when the
target is missed, which is how a pipeline stage can enforce a goal.

## Step 6 — Ratchet the budget

A saving with no budget is a saving that comes back next sprint.

Most repos only have a `bundle`-type budget on `main`, which does not constrain the eager set at
all. Add an `initial` budget and set the thresholds just above the number you just measured.

Take that number from the **`initial` budget basis** line of `bundle-report.md`, *not* from the
eager-JS row: Angular's `initial` budget counts eager JS **plus the initial CSS**, and a budget
ratcheted to eager JS alone fails on the commit that introduces it.

```jsonc
"budgets": [
  { "type": "initial", "maximumWarning": "<measured + 3%>", "maximumError": "<measured + 8%>" },
  { "type": "bundle", "name": "main", "maximumWarning": "<measured main + 3%>", "maximumError": "<measured main + 8%>" }
]
```

`ng build` already fails CI on a budget error, so this becomes the regression gate with no new
pipeline stage. Tighten it after every accepted candidate. `references/budgets.md` covers what
Angular counts under each budget type and why `initial` is the one that matters.

## Step 7 — Wire the analyzer into the repo

Add scripts so the next engineer does not need this skill to re-measure:

```jsonc
"analyze:prod":    "<BUILD_CMD> --configuration=production --stats-json && pnpm run analyze:report",
"analyze:report":  "node scripts/analyze-bundle.mjs --stats dist/stats.json --dist dist",
"analyze:compare": "node scripts/compare-bundle.mjs --baseline bundle-baseline.json --current bundle-report.json --md bundle-delta.md",
"analyze:deps":    "node scripts/analyze-deps.mjs --report bundle-report.json --md bundle-deps.md"
```

Copy the three analyzer `.mjs` files into the repo's `scripts/` directory (`test-analyze-deps.mjs`
is the skill's own self-check — `node scripts/test-analyze-deps.mjs` — and does not need copying). They are dependency-free Node ESM
— no analyzer package to install and no version to keep in sync. `analyze-deps.mjs` also takes
`--repos-root` when the local clones are not siblings of the app repo (default `..`).

Pass `--stats`/`--dist` explicitly when the repo's `stats.json` does not sit beside its assets;
Angular SSR builds write `dist/stats.json` while the browser assets land in `dist/browser/`.

## Step 8 — Report and MR

Artifacts produced by a full run, all at the repo root:

| File | Written by | Committed? |
| --- | --- | --- |
| `bundle-baseline.json` | Step 2 | yes — the reference every later number is relative to |
| `bundle-report.json` / `.md` | Step 5 | no — regenerated by `analyze:report` |
| `bundle-delta.md` | Step 5 | no — its table goes into the MR description |
| `bundle-deps.json` / `.md` | Step 3.5 | no — regenerated by `analyze:deps`; the per-repo table goes into the MR |

The MR description must contain the `bundle-delta.md` table, the list of candidates applied, and
the list demoted to REPORT with reasons. Headline the metric the stakeholder asked for, with the
eager number beside it.

It must also end with a **Conclusion — what can still be improved**, built from the
"What to improve next" table and stating, in this order:

1. which metric hit its target and which did not, with the KB still to remove (`--goal` output);
2. the next two or three candidates by pattern, with the estimate labelled as an estimate;
3. what is *not* worth attacking — the framework floor, and any package whose eager importer is
   owned by another team, named so the reader does not re-litigate it next sprint;
4. whether a target is reachable at all with the patterns left. Say so plainly when it is not.
   A capped honest number beats a number reached by moving bytes between eager chunks.

Commit convention: `perf: <what was deferred> (<metric> −<N>%)`. Branch off `master`, never commit
to `master` directly, open the MR against `master`.

Raise the MR with the repo's own tooling — do not hand-roll a git push flow. Prefer, in order:

1. an org commit/MR skill if one is loaded (check the available-skills listing);
2. a git-host MCP tool, resolved by search rather than a hardcoded name — `ToolSearch` for
   `create_merge_request` / `create_pull_request` — because the tool id carries the configured
   server name (`mcp__<server>__create_merge_request`);
3. the host CLI as a last resort: `glab mr create --target-branch master` or
   `gh pr create --base master`.

## References

- `references/detection.md` — toolchain detection lookups and fallbacks
- `references/analyzers.md` — how the metafile walk works, and how to read the output
- `references/playbook.md` — the reduction pattern catalog
- `references/budgets.md` — Angular budget types and the ratchet
- `references/internal-libraries.md` — attributing eager bytes to the owning shared repo, and
  deciding whether a fix is upstream or local procedure
