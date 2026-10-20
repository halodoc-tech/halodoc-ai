# web-bundle-optimizer

Measure and reduce the first-load JavaScript of an Angular app built with `@angular/build` (esbuild) — by the bytes a browser actually downloads before the first render, not just `main-*.js`.

## What it does

`main-*.js` is usually only 10–15% of the first load; the rest sits in `chunk-*.js` files that `main` imports statically and `index.html` preloads. Tracking `main` alone understates the cost and rewards moving code between eager chunks. This skill measures the **eager set** — everything reachable from the initial `<script>` / `modulepreload` tags, skipping dynamic `import()` edges — and reports it alongside `main`.

The flow runs in eight steps:

1. **Detect** — builder, package manager, prod configuration, SSR/zoneless/Native Federation. Stops on webpack builds.
2. **Baseline** — `ng build --stats-json`, then walk the esbuild metafile into an eager/lazy report.
3. **Attribute** — every eager byte to an npm package, then to the shared repo that owns it, with a tree-shaking probe per library.
4. **Rank** — candidates from a six-pattern playbook, ordered by simulated KB saved, not by how easy they are to explain.
5. **Apply one** — a single fix per commit.
6. **Re-measure** — before/after delta; flags the case where `main` falls but the eager total does not.
7. **Ratchet** — tighten the `initial` budget in `angular.json` so the win cannot regress.
8. **Raise the MR/PR** — with the before/after table.

## When it triggers

- "reduce the bundle size" / "analyze the bundle" / "why is our main bundle so big"
- "what's in main.js" / "shrink initial load" / "add a bundle budget"
- "how much does `<package>` cost us" / "which shared library is making us heavy"

## Scripts

All dependency-free Node ESM — copy them into your repo's `scripts/` to re-measure without the skill.

| Script | Purpose |
|---|---|
| `scripts/analyze-bundle.mjs` | metafile → per-package eager report (JSON + Markdown) |
| `scripts/analyze-deps.mjs` | eager bytes → owning repo, packaging vs usage verdict, `--trace <package>` to list every eager importer |
| `scripts/compare-bundle.mjs` | two reports → delta table; `--min-reduction` gates a pipeline |
| `scripts/test-analyze-deps.mjs` | the skill's own self-check |

Point `analyze-deps.mjs` at your own internal packages with `--scopes @your-org,...` and `--owner-hosts your-git-host` (matched against each package's `repository` / `homepage`).

## Requirements

- Angular on the `@angular/build` (esbuild) builder — `--stats-json` must emit a metafile.
- Node 18+.

## Results

On the Halodoc website: eager JS −19.3% (2,656.5 KB → 2,144.5 KB) and `main` −60% (308.4 KB → 123.3 KB), with no visual change.
