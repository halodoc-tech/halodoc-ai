# Pre-flight Checklist

Run through this checklist before starting any Angular upgrade.

## 1. Version Detection

Read `package.json` and extract:

| Package | Current Version | Field |
|---------|----------------|-------|
| @angular/core | ? | dependencies |
| @angular/cli | ? | devDependencies |
| @angular/material | ? | dependencies |
| @angular/cdk | ? | dependencies |
| @angular/ssr | ? | dependencies |
| typescript | ? | devDependencies |
| rxjs | ? | dependencies |
| zone.js | ? | dependencies |
| express | ? | dependencies |

For each dependency entry in both `dependencies` and `devDependencies`, record:
- Current version (exact string in `package.json`)
- Resolved version (from lock file if present)
- Whether the version is a range (`^`, `~`, `*`) or pinned

## 2. Project Classification

### SSR Detection
- Check `angular.json` → `projects.<app>.architect.build.configurations.*.ssr`
- If `ssr.entry` exists (e.g., `"entry": "src/server.ts"`), project uses SSR
- Check `outputMode` value: `"server"` = full SSR, `"static"` = pre-rendering only

### Express Server Detection
- Check if `src/server.ts` exists
- If yes, scan for:
  - `AngularNodeAppEngine` usage
  - `createNodeRequestHandler` export
  - Custom middleware (CSP, nonce, Prometheus)
  - Number of redirect routes

### Internal Package Detection
Search `package.json` for these prefixes:
- `@your-org/*` - internal utilities (eslint-config, feature-flags, media-utils, etc.)
- `@web-shared/*` - shared web libraries (auth, core, shared, pipes, i18n-loaders, etc.)
- `@design-system/*` - Design system (atoms, molecules, organisms, templates, design-tokens)
- `@platform/*` - micro-frontend fleet shared singletons (if present)

Note: Internal packages often use `-rc.X` suffixes indicating pre-release versions for Angular compatibility.

### PM2 Detection
- Check for `ecosystem.*.config.js` files (prod, stage, preprod)
- These configure PM2 cluster mode and pm2plugin for monitoring

### Micro-frontend Federation Detection
- **Native Federation** (supported): `@angular-architects/native-federation` or `@angular-architects/native-federation-v4` in `package.json`; `federation.config.js` / `federation.config.mjs`; an `@angular-architects/native-federation:*` builder in `angular.json`; a `federation.manifest.json`.
- **Module Federation** (NOT supported → hard stop): any `*module-federation*` package — `@angular-architects/module-federation*` or the internal `@your-org/module-federation`; `webpack.config.js` with `ModuleFederationPlugin`/`withModuleFederationPlugin`; `ngx-build-plus` / `@angular-builders/custom-webpack` builder.
- If Native Federation: record **role** — `exposes` in `federation.config.*` ⇒ remote; `remotes` / a loaded `federation.manifest.json` ⇒ host (`dynamic-host` if loaded at runtime) — and the **remote inventory** (whether remotes live in this repo or others).
- Full detection, package-name↔Angular-major map, and the cross-repo lockstep hard-stop: `references/native-federation.md`.

### Library Workspace Detection
- **Publishable Angular library workspace** (ng-packagr — the repos behind `@platform/*`, `@design-system/*`, `@web-shared/*`): `angular.json` `projects.*` of type `library`; `ng-packagr` in devDependencies; `projects/<lib>/ng-package.json`; per-library `projects/<lib>/package.json` with `peerDependencies`; root `private: true` + a publish script; no `federation.config.*` / app bootstrap.
- If detected, this is a **library upgrade** (not an app upgrade) — follow `references/library-upgrade.md`. For a federated fleet, upgrade the shared-library repos **before** the host/remotes.

### Test Framework Detection
- Check for `karma.conf.js` → Karma + Jasmine
- Check for `vitest` in devDependencies → Vitest (may coexist)
- Check test scripts in `package.json`: `test`, `test:ci`, `test:headless`

### Monorepo Detection
- Check for `pnpm-workspace.yaml`, `nx.json`, `lerna.json`, or `projects/` folder
- If monorepo, read every workspace `package.json`

## 3. Package Manager & Command Map Detection

### Package Manager
```bash
ls pnpm-lock.yaml yarn.lock package-lock.json bun.lockb 2>/dev/null
node -v
npx ng version 2>/dev/null
```

### Command Map
Build from `package.json` scripts. Use the actual script names — do not assume:

| Needed for | Look for in scripts (priority order) |
|------------|--------------------------------------|
| Install | `pnpm install` / `yarn install` / `npm install` / `bun install` (from lock file) |
| Build | `build`, `build:prod`, `prod-build`, `build:stage`, `compile` |
| Tests (CI-safe) | `test:ci`, `test:headless`, `test:unit`, `test` |
| Lint | `lint`, `eslint`, `lint:check` |
| Lint Fix | `lint:fix`, `lint-fix`, `lint -- --fix` |

## 4. Private Registry Configuration

Check `.npmrc`, `.yarnrc.yml`, or workspace config for private registry entries. These packages require special auth and may not be freely upgradable.

## 5. Fetch Official Angular Update Guide (MANDATORY)

This fetch is performed as **Phase 0D** in `SKILL.md` — it downloads the Angular `recommendations.ts` for the target version to `AI/angular-update-guide-v{TO}.ts` (with a release-notes fallback if the file is missing or empty). See Phase 0D for the exact commands and the data-structure reference.

**Every entry it produces must be audited in Phase 3B. No exceptions.**

## 6. Risk Assessment Matrix

| Factor | Low Risk | Medium Risk | High Risk |
|--------|----------|-------------|-----------|
| SSR | No SSR | SSR with standard setup | Custom Express server with CSP/nonce |
| Federation | None | Native Federation remote (self-contained) | Native Federation host with remotes in other repos (lockstep) |
| Internal packages | 0 | 1-5 | 6+ |
| Express version | Already on latest | One major behind | Multiple majors behind |
| Test count | < 100 tests | 100-500 tests | 500+ tests |
| Module count | < 5 | 5-15 | 15+ lazy modules |
| Major version jump | 1 major | 2 majors | 3+ majors |

Log the risk level and proceed immediately.

## 7. Pre-upgrade Snapshot

Before making any changes, capture full output to logs (the tail is just a quick glance — Karma's last 20 lines are usually only the summary banner, so a small `tail` hides which specs were already failing):
```bash
# Current build status
pnpm build:stage 2>&1 | tee AI/baseline-build.log | tail -5

# Current test status
pnpm test:headless 2>&1 | tee AI/baseline-test.log | tail -40

# Current lint status
pnpm lint 2>&1 | tee AI/baseline-lint.log | tail -10
```

This establishes a baseline. If any already fail, log it (the full output is in the `AI/baseline-*.log` files) — do not attempt to fix pre-existing issues during the upgrade.

## 8. Discovery Summary Template

```
Project:         <name from package.json>
Package Manager: <detected> (v<version>)
Node.js:         v<version>
Current Angular: v<version of @angular/core>
Target Angular:  v<version from prompt>
TypeScript:      <version>
Test Runner:     <karma|jest|vitest|other>
Monorepo:        <yes — tool / no>
SSR:             <yes — outputMode / no>
Express:         <yes — version / no>
PM2:             <yes — N configs / no>
Federation:      <native (host | remote | host+remote) — remotes in-repo/other-repo / none>
Internal Pkgs:   <N packages across M namespaces>

Dependency Groups Found:
  Group 1 Angular Core:        <N> packages
  Group 2 CLI & Build:         <N> packages
  Group 3 CDK & Material:      <N> packages  (or "not present")
  Group 4 Companions:          <N> packages
  Group 5 Third-Party Angular: <N> packages
  Group 6 Internal/Private:    <N> packages  (or "not present")
  Group 7 Non-Angular:         <N> packages

Resolved Commands:
  Install:  <command>
  Build:    <command>
  Test:     <command>
  Lint:     <command>
  Lint Fix: <command>

Node.js Compatibility:
  Angular v<target> requires Node.js v<min>.
  Current Node.js: v<current>   ← <OK / WARNING: below minimum>
```
