# Upgrading Angular Library Workspaces

This reference covers upgrading a **publishable Angular library workspace** (ng-packagr) to a target
Angular major — a **different flow** from the application upgrade the rest of the skill describes. The
deliverable is not a running app; it is **rebuilt libraries whose published `peerDependencies` allow the
target Angular**, so consuming apps (including Native Federation hosts/remotes) can adopt them.

**For a Native Federation fleet, upgrade the shared-singleton library repos FIRST** (e.g.
`your-group/platform-common` → `@platform/*`; the `@design-system/*` and
`@web-shared/*` repos), then the host, then the remotes. A lib built for Angular vN cannot load in
an app on a different major, so the fleet can only move once its shared libraries publish target-major builds.

## Contents
- Detection — is this a library workspace?
- Why the flow differs from an app upgrade
- Upgrade flow (steps 1–8)
- Publishing is a gated release action
- What NOT to assume

## Detection — is this a library workspace?

Classify the repo as a **library workspace** (not an app) when it shows these signals:

- `angular.json` has one or more `projects.*` with `"projectType": "library"` (builder
  `@angular-devkit/build-angular:ng-packagr` or `@angular/build:ng-packagr`).
- `ng-packagr` in `devDependencies`; a `projects/<lib>/ng-package.json` per library.
- A **per-library publish manifest** `projects/<lib>/package.json` carrying `peerDependencies`.
- Root `package.json` is `private: true` with **publish scripts** (e.g. `publish-module`) rather than an
  app `build`/`start` targeting a browser bundle. No `federation.config.*` / no app `src/main.ts` bootstrap.

A repo can hold **several** libraries (e.g. `platform-common` publishes `@platform/core`,
`@platform/shared`, and a handful of UI libraries; another shared workspace may publish a dozen or more).
Enumerate them from `angular.json` `projects` (type `library`) and their `projects/<lib>/package.json`.

**Common convention (verified across several such library workspaces):** they are `angular.json`-based (**not** Nx) and expose
`build-module <lib>` / `publish-module <lib>` npm scripts that wrap `build-scripts/build.js` →
`ng build <lib> --configuration production` and a per-lib `npm publish` to the internal registry. Key on
those scripts to recognize and drive the build. See `references/internal-packages.md` for the
scope → source-repo map.

## Why the flow differs from an app upgrade

| Application flow (main SKILL.md) | Library-workspace flow (this file) |
|---|---|
| `ng build` / `build:prod` | the repo's **own** build script (e.g. `pnpm build-module` → `build-scripts/build.js`) — never assume `ng build` |
| SSR boot + `ng serve` HTTP-200 render check | **no runtime render** — gate is "each library builds + per-library tests pass" |
| success = green build/tests + app MR | success = **bumped `peerDependencies` + built dist + version bump + (gated) publish** |
| internal libs treated as read-only | **the libraries ARE the thing being upgraded** |
| one app | **N libraries**, each with its own manifest + peer contract |

The compatibility contract that unblocks consumers is each library's
`peerDependencies["@angular/*"]` — **not** its version number. Real example: `@platform/core@20.2.1`
peers `@angular/core: "19.1.6"` — the `20.2.1` is the lib's own semver, decoupled from the Angular line.
Bumping the version without bumping the peer range does **not** make it Angular-20-compatible.

## Upgrade flow

**1. Discover the workspace.**
- List library projects (`angular.json` `projects` of type `library`) and their dirs.
- Read the **command map from `package.json` scripts** — build/test/publish are usually **custom wrappers**
  (`build-module`, `publish-module`, `test:<lib>`) and typically **take a library argument**. Under the
  wrapper the build is a *per-project library* build — e.g. `ng build <lib> --configuration production` —
  and publish is per-lib `npm publish` to the internal registry. Use the actual scripts; don't default to
  a bare `ng build`. **Ignore any `build-replace`-style dev helper** — it may carry a hardcoded local path
  and is for local link-testing, not the upgrade.
- **Map inter-library dependencies → build/publish/bump ORDER.** A library may depend on a sibling
  (confirmed: `@platform/shared` peers `@platform/core`). Build, test, publish, and
  peer-bump in **topological order — dependencies first** (`core` before `shared`). Derive the order from
  `peerDependencies` (e.g. feed `dep dependent` pairs to `tsort`); a cycle means the graph is wrong.
  **Dependencies can be CROSS-REPO** — verified: `@web-shared/*` libs (in `web-shared`) peer
  `@design-system/{molecules,organisms,atoms}`. So the **base design-system repo
  (`your-group/design-system`) must be upgraded/published before the repos that consume it**
  (`web-shared`, `platform-common`). Treat the lib repos as a DAG, not a flat "libraries first" set.
- Note the package manager and the per-library publish manifests (`projects/<lib>/package.json`).

**2. Upgrade the workspace's own Angular deps** — same dependency-group order as an app
(`references/dependency-groups-and-order.md`):
```bash
npx ng update @angular/core@{TO} @angular/cli@{TO} --allow-dirty --force
{pkg-manager} add -D ng-packagr@{TO}        # ng-packagr must match the Angular major
```
Then CDK/Material, TypeScript, RxJS/Zone as required. The library's **own source is Angular code** — run
the **Phase 3B migration-guide audit** (SKILL.md) against it too; libraries hit the same deprecations and
breaking APIs as apps. For a **Native Federation** library that ships a `federation.config.*`, the
adapter/line rules in `references/native-federation.md` still apply.

**3. Bump each published library's `peerDependencies` — the core deliverable.**
For **every** `projects/<lib>/package.json`, raise the peer ranges to the target: `@angular/*`, and any
shared **singletons** the fleet pins (`@angular/material`, `rxjs`, `zone.js`, design-system deps). Match
the repo's existing convention (some pin exact, e.g. `"@angular/core": "19.1.6"`; some use `^`). Because
NF hosts on the v3/Classic runtime match singletons **exactly** (see `references/native-federation.md`),
prefer the **exact target version** the fleet reconciliation manifest pins, not a loose range.

Also bump **inter-library peers** (e.g. `@platform/shared`'s peer on `@platform/core`) to
the new sibling version, in the same topological order. **Peer-range strategy is a real decision:** an
*exact* pin (`"20.3.25"`) enforces strict fleet lockstep — every consumer must move at once; a *widened*
range (`">=19 <21"` / `"^19 \|\| ^20"`) lets v19 and v20 apps consume the same library during a **phased**
migration, but only declare a range the library actually builds and works against. Strict NF singleton
fleet → exact-per-manifest; widely-shared design-system lib → a range enables coexistence.

**4. Bump each library's version** per the repo's convention. Note the version is the lib's **own semver**
and need not equal the Angular major (evidence above) — follow how the repo already numbers releases.

**5. Build every library — in dependency order** (siblings a lib depends on first, e.g. `core` before
`shared`), per-library, fixing build errors per `references/build-fix-patterns.md`:
```bash
{pkg-manager} run build-module <lib>   # repo wrapper → `ng build <lib> --configuration production`
```
This is a per-project *library* build (takes a lib arg), not the app's default `ng build`.

**6. Run per-library tests** (`test:<lib>` targets) and fix failures per
`references/test-fix-strategy.md`. There is no app runtime/SSR check. If the workspace has a
**demo/playground app** (e.g. `library-playground`), building/serving it is the closest end-to-end
smoke test that the rebuilt libraries actually consume — use it instead of assuming nothing runs.

**7. Publishing is a GATED release action — see below.** Do not auto-publish.

**8. Commit + open the MR** (GitLab / `glab`, per Phase 9). One MR per library repo; the description lists
each library, its old→new peer range, and the version bump.

## Publishing is a gated release action

Publishing rebuilt libraries to the org registry is **high-blast-radius** — every consumer resolves the
new version. And the compatibility is directional: Angular libraries ship in **partial-compilation**
format, linked by the **consuming app's** Angular Linker, so a library built with the **target** ng-packagr
can emit partial output an **older** app's linker rejects — i.e. a target-major-built library generally
**breaks an app still on the old major** (the reverse — an older-built lib in a newer app — usually works
within ~one major). So:

- The skill **prepares** the release (peer bump + build + version + MR); it does **not** run
  `publish-module` automatically.
- Publishing is gated to a human / release pipeline, is **per-library in dependency order** (`core` before
  `shared`) to the internal registry, and must be **coordinated with the fleet lockstep**: publish the
  libraries, then upgrade host + remotes to consume them in the same major. Until then, consumers stay on
  the previous-major-built versions.
- If the platform team owns publishing, hand off after the MR merges rather than publishing directly.

## What NOT to assume

- **Not the app's plain `ng build` / `ng serve`** — libraries build **per project** via ng-packagr
  (`ng build <lib>`, usually a repo wrapper) and don't serve. No HTTP-200 runtime render gate applies.
- **The version number is not the compatibility signal** — the published `peerDependencies` range is.
- **Don't publish without lockstep** — a target-major library breaks an older-major consumer (partial-Ivy
  is forward-, not backward-compatible).
- **Build/publish/bump order follows inter-library deps** — a lib that peers a sibling goes after it.
- **Secondary entry points** (a nested `ng-package.json` under a lib) have their **own** `package.json` /
  peer set — bump each, not just the primary entry.
- **Re-exported deps** must be declared in the *re-exporting* library's own published `peerDependencies`,
  not only at the workspace root, or consumers can't resolve them.
