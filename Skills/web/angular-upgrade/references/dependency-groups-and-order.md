# Dependency Groups & Upgrade Order

Angular upgrades involve cascading dependency chains. Updating packages in the wrong order causes compounding peer dependency failures.

## Dependency Groups

Categorize every dependency in `package.json` (both `dependencies` and `devDependencies`):

| Group | What Belongs Here |
|-------|-------------------|
| **1 — Angular Core** | `@angular/core`, `@angular/common`, `@angular/compiler`, `@angular/compiler-cli`, `@angular/platform-browser`, `@angular/platform-browser-dynamic`, `@angular/forms`, `@angular/router`, `@angular/animations`, `@angular/ssr`, `@angular/service-worker` |
| **2 — Angular CLI & Build** | `@angular/cli`, `@angular-devkit/*`, `@angular/build`, `@angular-eslint/*`, `angular-eslint`, and (if federated) the **Native Federation** adapter `@angular-architects/native-federation[-v4]` + `@softarc/native-federation*` — version-locked to the Angular major, see Step 2b. **Never** `@angular-architects/module-federation*` (unsupported — Phase 0B hard-stops). |
| **3 — Angular CDK & Material** | `@angular/cdk`, `@angular/material` |
| **4 — Angular Companions** | `@angular/language-service`, `zone.js`, `rxjs`, `tslib`, `typescript` |
| **5 — Third-Party Angular Libs** | Packages with `ngx-`, `@ngx-`, or that peer-depend on `@angular/core` (e.g., `@ngx-translate/core`, `ngx-infinite-scroll`, `ngx-pagination`, `ng2-pdf-viewer`, `ngx-ellipsis`, `ngx-device-detector`, `swiper`) |
| **6 — Internal / Private Packages** | `@your-org/*`, `@web-shared/*`, `@design-system/*`, `@platform/*` — treat as read-only unless user explicitly asks. See `references/internal-packages.md` |
| **7 — Non-Angular Dependencies** | Everything else: utility libraries, CSS frameworks, non-Angular testing tools |

Not every project has every group. Only work with what exists.

## Strict Upgrade Order

Execute in sequence. Do NOT skip ahead.

### Step 1: Angular Core + CLI

```bash
ng update @angular/core@{TARGET} @angular/cli@{TARGET} --allow-dirty --force
```

The `--force` flag bypasses peer dependency checks from internal packages; `--allow-dirty` lets it run on a working tree that already has changes (consistent with SKILL.md Phase 3 — without it, `ng update` aborts on any uncommitted change). After this step, run `pnpm install` and verify lock file consistency.

> `ng update` has no `--dry-run` flag. The command executes immediately. To preview, run `npx ng update` (without a package argument) to see available updates.

### Step 2: Angular Build Tools

```bash
pnpm update @angular/build@{TARGET} @angular-devkit/build-angular@{TARGET}
```

Must match Angular core version for the build system to work.

> **Pre-v18 projects:** `@angular/build` did not exist before Angular 18. A v17→v18 (or earlier) project starts with only `@angular-devkit/build-angular`, and migrating to the new builder means flipping `angular.json`'s `builder` from `@angular-devkit/build-angular:browser` to `@angular/build:application`. The Phase 3B migration-guide audit should surface this, but verify it explicitly — otherwise the recommendation is "applied" yet the build still runs on the old builder.

### Step 2b: Native Federation Adapter (if federated)

Upgrade the adapter here — after Angular core + CLI, before Material — because it delegates to Angular's `ApplicationBuilder` and must match the just-installed Angular. Pick the package by target major, and note that the **v4 line is only mandatory at Angular 22+**:

| Target Angular | Adapter package | NF line / config |
|----------------|-----------------|------------------|
| ≤ 19 | `@angular-architects/native-federation` (Angular-major-aligned) | v3 · `federation.config.js` (CommonJS) |
| 20 / 21 | `@angular-architects/native-federation-v4` (recommended) — or keep an existing v3 install | v4 (recommended) / v3 (retained) |
| 22+ | `@angular-architects/native-federation@22.x` | v4 · `federation.config.mjs` (ESM), mandatory |

The v4 line is mandatory only at Angular 22+. On Angular 20/21 the recommended package is `@angular-architects/native-federation-v4`, which runs v4 **without upgrading Angular to 22**; an app already on v3 may stay on v3 (supported ≤21) as the lower-churn option. The decision hinges on the project's **current** line — if already on v4, just bump the v4 package (no config migration); if on v3 targeting 20/21, **ask** whether to adopt `-v4` now. Resolve exact versions via `npm view` — don't assume numbers. See "The v4 decision on Angular 20/21" in `references/native-federation.md`.

```bash
# When landing on the v4 line (target 22+, or opt-in on 20/21): wipe stale caches first —
# the emitted module format changes. (Skip this for a plain 20/21 bump staying on v3.)
rm -rf dist .angular node_modules/.cache
npx ng update @angular-architects/native-federation@{ADAPTER_TARGET} --allow-dirty --force
# v4 opt-in on Angular 20/21 uses the backport package: @angular-architects/native-federation-v4
```

The `ng update` schematic migrates the SSR server files (`bootstrap.server.ts` / `fstart.mjs`) and — **when moving onto the v4 line** — `federation.config.js` → `.mjs`/ESM. Verify it did: audit the v3→v4 checklist in `references/native-federation.md` during Phase 3B (only when landing on v4). Do **not** switch a server-rendered host to the Orchestrator runtime (client-only).

### Step 3: Angular Material + CDK

```bash
ng update @angular/material@{TARGET_MATERIAL} @angular/cdk@{TARGET_MATERIAL} --force
```

Material/CDK versions may not exactly match core (e.g., core 20.3.7, material 20.2.10). Check https://github.com/angular/components/releases for compatible version.

### Step 4: Angular SSR

```bash
pnpm update @angular/ssr@{TARGET_SSR}
```

SSR package version may differ from core. Check release notes.

### Step 5: TypeScript

Check required range:
```bash
npm view @angular/compiler-cli@{TARGET} peerDependencies.typescript
```

Update if current version is outside required range.

### Step 6: RxJS & Zone.js

```bash
npm view @angular/core@{TARGET} peerDependencies.rxjs
npm view @angular/core@{TARGET} peerDependencies.zone.js
```

Update if required. RxJS major bumps are rare but significant.

### Step 7: Third-Party Angular Libraries

Update in order of dependency (packages that depend on others go last). For each:
```bash
npm view {PACKAGE}@latest peerDependencies
```

Check Angular compatibility before upgrading.

### Step 8: Internal Packages

Update LAST because:
1. They depend on Angular core, so core must be updated first
2. They may need republishing by the internal package team
3. Using `--force` during core upgrade already handled their peer dep conflicts

See `references/internal-packages.md` for full strategy.

## Resolving Peer Dependency Conflicts

| Situation | Action |
|-----------|--------|
| Another package in same group needs upgrading first | Reorder — upgrade blocking package next |
| Third-party library requires old version | Find compatible newer version; skip if none |
| Strict peer dependency mode blocking (pnpm) | Add `strict-peer-dependencies=false` to `.npmrc` |
| Internal package peer conflict | Use `--force` for `@your-org/*`, `@web-shared/*`, `@design-system/*` only |
| Transitive dependency pins old version | Add `pnpm.overrides` in `package.json` (last resort, remove after dep publishes compatible version) |

## Post-Upgrade Verification

```bash
pnpm install
pnpm ls @angular/core  # Must show only ONE version
```

If multiple Angular versions appear, resolve with overrides.
