# Third-Party Package Compatibility

The official Angular update guide (fetched in Phase 0D) covers Angular's *own* breaking changes. It says nothing about third-party packages. This reference covers the gap: how to resolve third-party peer-dependency and bundling conflicts during an upgrade, plus a curated list of non-obvious package gotchas that no official source will warn you about.

## General Procedure (version-agnostic)

When upgrading Group 5 (third-party) packages, conflicts surface in two ways:

### 1. Peer-dependency block at install time

`npm`/`pnpm`/`yarn` refuses the install because a package declares an Angular peer range that excludes the target version.

Resolution order:
1. **Check for a newer version** of the package that declares support for the target Angular. Bump to it. This is the correct fix the large majority of the time.
2. **If no compatible version exists yet**, check whether the package actually *works* at runtime despite the stale peer range (many do — the peer range is often over-conservative). If it does, install with `--force` / `--legacy-peer-deps` and record it in the upgrade report as "running past declared peer range — monitor."
3. **If it neither has a compatible version nor works at runtime**, it is a blocker. Document it and flag to the user; do not patch `node_modules`.

### 2. Build-time "No matching export" / ESM bundling error

The package installs fine, but the build fails because a symbol the code imports is no longer exported from the package's ESM bundle. The `.d.ts` types may still declare the symbol, so the editor shows no error — only the bundler catches it.

Resolution order:
1. Check the package changelog for the version that removed/renamed the export and migrate to the new API.
2. If the export was removed with no replacement, **pin to the last version that still exports it** (verify it runs correctly against the target Angular), and plan a migration off the package.
3. Record the pin and the EOL risk in the upgrade report.

## Native Federation adapter (version-locked)

If the app is federated, `@angular-architects/native-federation` is **not** a loose "latest that supports v{TO}" Group-5 bump — it is version-locked to the Angular major like CDK/Material, and installing the wrong package for the line is itself a break. The line rules (v3 vs v4, and the 20/21 decision) are defined once in `references/native-federation.md` → "Adapter package selection"; the operational step is Step 2b of `references/dependency-groups-and-order.md`. The only thing that matters for *this* file: the adapter is handled in **Phase 3**, never swept as part of the Phase 8B third-party pass.

Also: any third-party library marked `singleton: true` in `federation.config.*` (state libs, design-system packages) must resolve to the **same** version across **host and all remotes**, or runtime singleton negotiation warns/breaks. These are reconciled and pinned **before** the upgrade (see "Cross-repo singleton reconciliation" in `references/native-federation.md`). In this Phase 8B sweep, **do not bump a singleton past its reconciled pin** — freeze singletons to the agreed manifest and only sweep non-singleton third-party libs. Flag any singleton that needs a different version as a cross-repo decision, not a unilateral bump.

## Major-version bumps: read the release notes FIRST

The build + test gate catches **compile-time** breaks and breaks in **already-covered** behavior. It does
**not** catch runtime-only/behavioral changes, silent deprecations, renamed inputs/config keys, or
peer/CSS-token changes that no existing test exercises. So for any **major-version** bump of a third-party
package (current major < target major), **read the package's release notes / migration guide for every
crossed major BEFORE relying on the build**, and apply the documented breaking-change migrations:

- Sources, in order: the repo's `CHANGELOG.md` / `UPGRADING.md` / `MIGRATION.md`, then GitHub Releases
  (`https://github.com/<owner>/<repo>/releases`), then the npm page / project docs. Use WebFetch/WebSearch.
- Apply the documented codemods/migrations, **then** run the build + specs to confirm — don't invert this
  order and hope the build surfaces everything.
- Record in the report which majors were crossed and which migration steps were applied.

For **minor / patch** bumps, semver implies no breaking changes — the build + test gate is sufficient; skip
the changelog read unless a break actually surfaces at build/test time.

## Known Package Gotchas

These are keyed by **package version**, not Angular version — they hold regardless of which Angular you are targeting.

| Package | Trigger | Symptom | Resolution |
|---------|---------|---------|------------|
| `ngx-extended-pdf-viewer` | Tight Angular peer range on older majors | Peer-dep block at install when bumping Angular | Bump in lockstep with Angular — this package pins a narrow peer range and almost always needs a matching major bump |
| `ngx-panzoom` `>=18.0.0` | v18 removed `PanZoomConfig` from the ESM (`fesm2022`) bundle — it survives in `.d.ts` only | Build-time "No matching export" for `import { PanZoomConfig } from 'ngx-panzoom'`. Editor shows no error because the type still exists | Pin at `17.0.0` (last version that exports `PanZoomConfig` from JS). EOL as of v19 — plan a migration to `@panzoom/panzoom` for any consuming libraries |

### `ngx-panzoom` detail

`ngx-panzoom@17.0.0` exports `{ NgxPanZoomModule, PanZoomComponent, PanZoomConfig }` in its `fesm2022` bundle. Starting with v18, `PanZoomConfig` was removed from the JS exports (it remains in `.d.ts` only). Any code or private library that does `import { PanZoomConfig } from 'ngx-panzoom'` will produce a build-time "No matching export" error with Angular's bundler, even though the type-checker is happy. The "obvious" fix of bumping the version to clear the peer-dep warning makes this *worse*. The package is end-of-life as of v19.

## Post-Angular Review & Upgrade (Phase 8B)

Phase 3 only touches a third-party package when it actively blocks the install or build. That leaves working-but-outdated packages behind. **After** the Angular upgrade is build-green and tests pass, go through **every** third-party (Group 5) Angular-ecosystem package and bring each up to the highest version compatible with the target Angular — don't stop at the ones that happened to break the build.

1. **Enumerate all** third-party Angular-ecosystem packages from `package.json` (use `{pkg-manager} outdated` as a hint, but cover the full list, not just what it flags).
2. **Resolve each package's target version** — the newest published version whose Angular peer range includes v{TO}:
   ```bash
   npm view {package} versions --json                # all versions
   npm view {package}@{candidate} peerDependencies   # does this version support Angular v{TO}?
   ```
   Target `latest` if it supports v{TO}; otherwise the newest version that does.
3. **Upgrade each to its target version**, one at a time, with a `{build-command}` gate and a re-run of the specs it touches (same circuit breakers as Phase 3).
4. **Defer only when forced**: if there is no v{TO}-compatible release, or the only compatible version needs a deeper code migration (API-contract change — e.g. NGX-translate-style) that can't be finished within the retry budget, revert that package to a working version, pin it, and record it. Attempt first; defer second; never skip silently.
5. **Report** in the upgrade report's "Third-Party Dependencies" section: upgraded (old → new), deferred (compatible but needs deeper migration), at-risk (no compatible release / maintenance / EOL → suggested alternative).

Scope discipline: keep this to the Angular ecosystem. Do **not** fold unrelated/non-Angular dependency bumps into the Angular upgrade — that is a separate task.

## Maintaining This File

Do **not** add per-Angular-version sections. When you discover a new third-party gotcha during an upgrade:
- Add a row to the table keyed by the **package version** that introduces the problem.
- Only record entries that are *actionable* (a block, a break, or a non-obvious pin). Do not record "package X needs no change" — that is the default assumption and only adds noise that goes stale.

> Gotchas last verified against Angular 21. If a listed resolution no longer applies on a later Angular, update or remove the row rather than adding a parallel version section.
