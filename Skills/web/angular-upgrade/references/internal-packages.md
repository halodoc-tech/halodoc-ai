# Internal Package Handling

Angular projects at your org commonly depend on internal packages across several scopes. These require special handling during Angular upgrades because they have their own release cycles.

## Package families

Internal packages usually cluster into a few scopes, each with its own release cycle. A typical shape:

| Scope | Role | Illustrative packages |
|---|---|---|
| `@your-org/*` | Miscellaneous internal utilities | `eslint-config`, `feature-flags`, `media-utils`, `monitoring-utils` |
| `@design-system/*` | Design system | `atoms`, `molecules`, `organisms`, `design-tokens`, `templates` |
| `@web-shared/*` | Shared web libraries | `core` (CRITICAL), `auth`, `cart`, `pipes`, `i18n-loaders` |
| `@platform/*` | Micro-frontend fleet shared libraries | `core`, `shared` |

> These names are illustrative only. The exact set a project consumes varies — always derive the current package list and versions from the target project's `package.json`; never assume the inventory from this document.

## Library source repositories (where to upgrade a singleton)

Each internal namespace is **published from its own Angular library workspace** (ng-packagr). To make a
singleton support a new Angular major, upgrade its **source repo** with `references/library-upgrade.md`:

| Published scope | Source repo (GitLab `your-group/…`) |
|---|---|
| `@platform/*` | `your-group/platform-common` |
| `@design-system/*` | `your-group/design-system` |
| `@web-shared/*` | `your-group/web-shared` |
| `@your-org/*` (web commons) | `your-group/web-commons` |
| micro-commons | `your-group/micro-commons` |

All five share one convention (verified): `build-module <lib>` / `publish-module <lib>` npm scripts
wrapping `build-scripts/build.js` → `ng build <lib> --configuration production`; **angular.json-based, not
Nx**; multi-library; publishing per-lib to your private registry.

**They sit on DIFFERENT Angular majors.** As of mid-2026, `platform-common` is on Angular **19** while
`design-system`, `web-shared`, `web-commons`, and `micro-commons` are on **21** — so a single consuming
app's singletons come from repos at different majors (some already **ahead** of the app's target). During
reconciliation, resolve **each** singleton's source repo and its current major; converging an app on one
target may require upgrading (or waiting on) several of these lib repos in their own right.

**The lib repos also form a cross-repo dependency DAG.** Verified: `@web-shared/*` (in `web-shared`)
peers `@design-system/*` components — so **upgrade the base design-system repo (`your-group/design-system`) before the repos
that consume it** (`web-shared`, `platform-common`, `micro-commons`), then the apps. Derive the
order from each library's `peerDependencies` (`tsort`), not a hardcoded list. Fleet order overall:
**base lib repos → dependent lib repos → host → remotes.**

## Upgrade Strategy for Internal Packages

### Step 0: Pre-flight — does a target-major build EXIST? (federated fleets: STOP-class)

Before touching anything, for each internal package that is a **federation `singleton`** (shared across host + remotes — especially `strictVersion: true`, e.g. `@platform/*`, `@web-shared/core`, `@design-system/*`), resolve whether a published build exists whose Angular peer range **includes the target major**:

```bash
npm view <pkg> versions --json                 # all published versions (incl. -rc)
npm view <pkg>@<candidate> peerDependencies     # does its @angular/core peer include v{TO}?
```

If **no** compatible build exists for a shared singleton, there is **no coherent target-Angular dependency set for the fleet** — the apps are blocked **upstream** until the library publishes a target-major build. The fix is to **upgrade that library repo FIRST**: the library workspaces behind `@platform/*`, `@design-system/*`, `@web-shared/*` (e.g. `your-group/platform-common`) can themselves be upgraded with this skill's **library mode** — see `references/library-upgrade.md` (bump each library's `peerDependencies` to the target, rebuild via the repo's own script, then a gated publish). Upgrade order for a fleet: **shared-library repos → host → remotes.** **STOP and report** only when the library repo isn't available for you to upgrade (then it's a platform-team release action).

Real-world shapes to expect and document:
- A lib peers the **previous** major with no target build (e.g. `@platform/core` peers Angular 19, newest RC still 19) → the host can keep running on the previous-major-built singletons via library forward-compat **only if** every repo stays pinned to the same version so the singleton contract holds. Record this in the reconciliation manifest.
- A lib **skips** the target major entirely (e.g. jumps Angular 19 → 21, no 20 build) → there is no path to the skipped major for that fleet; report and stop.

### Step 1: Check if compatible versions exist

Before the upgrade, check if Angular-{TARGET}-compatible versions of internal packages have been published. The team typically publishes new versions with `-rc.X` suffixes before the main app upgrade.

Look for patterns in `package.json`:
- `-rc.X` suffix = pre-release for Angular compatibility
- Major version bumps usually align with Angular major versions

### Step 2: During `ng update`

When running `ng update @angular/core @angular/cli`, internal packages will cause peer dependency conflicts. This is expected.

**Strategy:**
1. First attempt: `ng update @angular/core@{TARGET} @angular/cli@{TARGET}`
2. If it fails with peer dependency errors from `@your-org/*`, `@web-shared/*`, or `@design-system/*`:
   - Re-run with `--force` flag to bypass internal package peer dependency checks
3. After force-updating core Angular, update internal packages to their compatible versions

### Step 3: Internal package version updates

If the team has published Angular-{TARGET}-compatible versions:
```bash
pnpm update @web-shared/core@{NEW_VERSION} @design-system/atoms@{NEW_VERSION} ...
```

If compatible versions are NOT yet published:
- Document which packages need republishing in the upgrade report
- The upgrade can proceed with `--force` but may have runtime issues from incompatible peer deps
- Flag this to the user as a blocker that requires the internal package team to act

### Step 4: Verify no broken imports

After updating internal packages, common issues:
- **RxJS import changes**: Internal libraries may import from `rxjs/internal/*` which breaks between versions
- **Angular API changes**: Libraries may use deprecated Angular APIs
- **Type mismatches**: TypeScript version bumps can expose type issues in library type definitions

These errors will surface during the build phase (Phase 3) and should be fixed there.

## What You Cannot Fix

Some internal package issues require the package to be republished:
- If a library imports from a path that no longer exists in the new RxJS/Angular version
- If a library's compiled `.d.ts` files reference removed types
- If a library bundles Angular code that's incompatible with the new version

Document these in the upgrade report and flag them to the user. Do not attempt to patch `node_modules`.
