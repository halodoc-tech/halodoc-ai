# Native Federation Upgrades

This reference covers upgrading Angular applications that use **Native Federation**
(`@angular-architects/native-federation`) — micro-frontend hosts and remotes built on ESM +
Import Maps that delegate to Angular's esbuild `ApplicationBuilder`.

## Contents
- **Scope** — Native Federation only, not Module Federation
- **Detection** (Phase 0B) — NF vs MF signals, host/remote role, current v3/v4 line
- **Cross-repo lockstep — HARD STOP** — hosts whose remotes live in other repos
- **Cross-repo singleton reconciliation** — reconcile/pin shared singletons *before* upgrading; exact-pin rationale (runtime matching); assisted discovery script
- **Adapter package selection** — target major + current line; the v4 decision on Angular 20/21
- **Upgrade procedure** (Phase 3) · **v3→v4 breaking-change checklist**
- **Angular 20 build layout** — `tsconfig.app.json` + `federation.config.js` must move to repo ROOT (v3 adapter)
- **SSR with Native Federation** (Phase 4) — `fstart.mjs`, Classic Runtime, prerender-at-build
- **Import maps, es-module-shims & CSP** — internal nonce interaction
- **Runtime verification** · **Deployment** (PM2/checklist) · **Third-party dependencies**

## Scope: Native Federation only — NOT Module Federation

This skill supports **Native Federation** as the micro-frontend stack. It does **NOT** support the
older **webpack Module Federation** (`@angular-architects/module-federation`,
`@angular-architects/module-federation-runtime`, `ModuleFederationPlugin`, `webpack.config.js`,
`ngx-build-plus`, `@angular-builders/custom-webpack`).

If Module Federation is detected (see Detection below), **STOP** and tell the user:

> This app uses webpack Module Federation, which this skill does not support. Migrate to Native
> Federation first (`ng g @angular-architects/module-federation:remove` →
> `ng update @angular/cli --name use-application-builder` →
> `ng add @angular-architects/native-federation`), then re-run the upgrade. See
> https://native-federation.com/docs/migration.html

Do not attempt a webpack-Module-Federation upgrade.

## Detection (Phase 0B)

Run these checks after the standard SSR/Express detection.

**Native Federation present** — any of:
- `@angular-architects/native-federation` or `@angular-architects/native-federation-v4` in
  `package.json` (dev dependency), or `@softarc/native-federation*`.
- A `federation.config.js` or `federation.config.mjs` at the project root.
- `angular.json` `architect.build.builder` (or `serve`) is `@angular-architects/native-federation:*`
  (e.g. `:build`, `:esbuild`, `:dev-server`).
- A `federation.manifest.json` (usually under `public/` or `src/assets/`).
- **Nx**: the same signals live in per-app `project.json` targets/executors instead of `angular.json`
  (workspace marked by `nx.json`); config still uses `withNativeFederation`.

**Module Federation present** (→ hard stop) — any of:
- Any `*module-federation*` package in `package.json`: `@angular-architects/module-federation*` **or a common `@your-org/module-federation`** (its `withModuleFederationPlugin` wrapper).
- `webpack.config.js` / `webpack.prod.config.js` containing `ModuleFederationPlugin` or `withModuleFederationPlugin`.
- `ngx-build-plus` or `@angular-builders/custom-webpack` as the builder in `angular.json`.

If **both** Native and Module Federation signals appear (a repo mid-migration, or stale MF deps left
behind), do **not** silently proceed — ask the user which is authoritative. Only proceed for a project
that actually builds with Native Federation.

**Current NF line — v3 vs v4** (decides whether a config migration is in scope):
- v3: `federation.config.js` (`require` / `module.exports`), `@softarc/native-federation@3.x`.
- v4: `federation.config.mjs` (`import` / `export default`), `@softarc/native-federation@4.x`
  (adapter `native-federation-v4` on Angular 20/21, or `native-federation@22.x` on Angular 22+).

**Role — host vs remote** (from `federation.config.*`):
- `exposes: { ... }` present → this project is (at least) a **remote**.
- `remotes: { ... }` present, or a `federation.manifest.json` is loaded at bootstrap → this project
  is a **host** (`dynamic-host` if it loads the manifest at runtime).
- A project can be both. Record what it exposes and which remotes it consumes.

Record in the discovery summary: `Federation: native (host | remote | host+remote), line v3|v4 | none`.

## Cross-repo lockstep — HARD STOP

Host and remotes share Angular (and other libraries flagged `singleton: true`) as **runtime
singletons** negotiated through the import map. If the host loads a remote built against a different
Angular **major**, singleton negotiation fails at runtime (or two Angular copies load) — and a green
build will **not** catch it.

Therefore, when the target project is a **host that consumes remotes living in other repositories**
(remote URLs in `federation.config.*` / `federation.manifest.json` point outside this repo):

**STOP and require confirmation before proceeding.** Surface to the user:

> This is a Native Federation host. Its remotes ({list from manifest/config}) share Angular as a
> runtime singleton. Upgrading this host to v{TO} without upgrading those remotes to the same major
> can break singleton negotiation at runtime (a passing build won't detect it). Confirm that the
> host and all its remotes are being upgraded to Angular v{TO} in lockstep before I continue.

Proceed only after the user confirms lockstep **and the singleton reconciliation below exists** (or
they explicitly accept the risk in writing). Record the confirmation and the remote inventory in the
upgrade report's Federation section. If the remotes are in the **same** repo/monorepo, upgrade them
together in one run instead of stopping.

## Cross-repo singleton reconciliation — do this BEFORE upgrading ANY repo

Lockstep is **not** just "same Angular major everywhere." Shared singletons negotiate by **version** at
runtime. If each repo runs its upgrade independently, Phase 8B in each resolves a shared library to
"the highest version compatible with the target Angular" — and different repos can land on **different**
versions. That is exactly what breaks singleton negotiation (or silently loads two copies). A green
build in each repo will not catch it. So the **first** step of a federated upgrade is a one-time,
cross-repo reconciliation, run **before** any per-repo `/angular-upgrade`:

1. **Enumerate the singleton set.** From **every** repo (host + all remotes), read `federation.config.*`
   and collect the union of shared deps. Sharing is declared either as `shareAll({ singleton: true,
   strictVersion: true, requiredVersion: 'auto' })` (shares every runtime dependency) or — the actual
   pattern seen in practice — an explicit `share({ '@angular/core': {...}, '@platform/core': {...},
   '@ngx-translate/core': {...}, ... })` alongside a `skip: [...]`. With `strictVersion: true` a version
   **mismatch throws at runtime** (it doesn't just warn) — that is the **safe** case, because it announces
   itself. **`strictVersion: false` is the dangerous one**: combined with a highest-version-wins profile
   the negotiated winner is silently substituted for every repo — no throw, no console warning, smoke test
   green. Observed in a real fleet: all three singletons that drifted into production were
   `strictVersion: false`, one of them **nine majors** above what the host was compiled against. So treat
   a non-strict singleton as needing *more* verification than a strict one, and record `strictVersion`
   per singleton in the reconciliation manifest alongside the pin.

   Note also that **`requiredVersion: 'auto'` resolves to the exact installed version string, not a
   range** — which is precisely why any drift is fatal rather than tolerated. A fleet that wants
   tolerance must declare explicit semver ranges instead of `'auto'`; a shared contract package that
   exports the fleet's share map + ranges (imported and spread into each repo's config) is the
   maintainable way to keep those ranges identical everywhere.

   The discovery script parses the config
   and enumerates the **actual** shared set (explicit `share(...)` keys, or all `dependencies` under
   `shareAll`, minus `skip`) — so it captures the real singletons (`@platform/*`, `@ngx-translate/*`,
   design-system libs), not just the framework. **A static parse is a floor, not the set**: a config that
   spreads an imported share map (`share({ ...fleetShared, 'pkg': singleton(...) })`) keeps most package
   names in another package entirely, where no regex can reach them — those rows are marked `share(N)!`
   with a trailing `!`. Resolve the true set by *evaluating* the config in a checkout with dependencies
   installed (`references/post-deploy-verification.md` §1); on one real repo the static parse saw 1
   explicit key while evaluation resolved 152, and every drifting singleton was in the difference.
   The framework shortlist is **always unioned in as a
   floor** (framework drift matters for the upgrade even when a config doesn't share a package
   explicitly), and becomes the sole source when the config isn't at repo root / can't be parsed —
   the inventory's `shared` column says which happened: `share(N)` / `shareAll(N)` (parsed, N =
   candidates incl. the floor), `cfg?(N)` (config found but no recognizable share syntax), or
   `shortlist(N)` (no root config). For the ultimate ground truth of a `shareAll` fleet, also diff the
   resolved lockfile versions across repos — e.g. per repo
   `jq -r '.packages | to_entries[] | "\(.key)@\(.value.version)"' package-lock.json | sort` (or the
   `pnpm-lock.yaml` / `yarn.lock` equivalent), then compare — because `shareAll` shares transitive deps
   the config never names. Note also: a package skipped in ONE repo but shared in others still appears in
   the manifest — check `observed` coverage per repo before pinning.
2. **Pick ONE target version per singleton** that all repos will share — the version compatible with the
   target Angular. Pin the Angular framework packages to the **exact target patch** (e.g. `22.0.3`, not
   `^22`); resolve each other singleton to the newest version whose peer range includes the target. For an
   **internal singleton** (`@platform/*`, `@web-shared/core`, `@design-system/*`) with **no** published build whose
   peer includes the target major, **upgrade that library repo first** — its workspace can be upgraded with
   this skill's library mode (`references/library-upgrade.md`): bump its `peerDependencies` to the target,
   rebuild, publish; then the apps. STOP only if the library repo isn't available to you. See
   `references/internal-packages.md` (Step 0).
3. **Record the agreed pins** in a shared manifest that every repo's run consumes — e.g. a committed
   `federation-shared-versions.json`, or `AI/federation-singletons.json`. This is the single source of
   truth for the upgrade.
4. **Feed the pins into each per-repo run.** Each repo installs the reconciled singletons at the **exact**
   agreed version, and **Phase 8B must NOT bump a singleton past the agreed pin** — it may sweep
   non-singleton third-party libs freely, but the singletons are frozen to the reconciled set. Also make
   each repo's `federation.config.*` `requiredVersion` / version strategy mutually satisfiable.
5. **Then upgrade the repos in fleet order — shared-library repos first** (`references/library-upgrade.md`,
   so the target-major singletons exist to pin against), and **among the lib repos follow their cross-repo
   dependency order — base design-system (`@design-system`) before the repos that consume it (`@web-shared`,
   `@platform`)** — **then the apps (remotes, then host)**, each consuming the manifest.

Skipping this makes every repo "do its best" independently and drift apart on singleton versions — the
failure mode a green build never reveals (and with `strictVersion` it's a hard runtime throw).

### Why the pins must be EXACT (runtime version matching)

How strictly versions must match depends on the runtime:

- **v3 / Classic Runtime — and ANY SSR host** (the v4 Orchestrator is client-only): **strict version
  matching**. Even a **patch** difference across repos (host `19.1.5` vs remote `19.1.6`) is treated as
  incompatible → the runtime loads **two separate instances** of the singleton (or throws under
  `strictVersion`). So for a v3 fleet, and for the SSR host in *any* fleet, pin each singleton to **one
  exact version** — no `^`/`~`. This is why one fleet's `zone.js` `~0.15.0` vs `~0.15.1` and `rxjs` `6.5.4`
  vs `7.8.2` are **real breakage today**, not cosmetics.
- **v4 Orchestrator (client-side only):** adds **semver-range resolution** — remotes declaring different
  compatible ranges are reconciled automatically, so patch/minor drift is tolerated. This does **not**
  apply on the SSR path (Classic Runtime), so SSR hosts still need exact pins.

Mixed NF **lines are fine**: a **v4 host can load v3 remotes** (the `remoteEntry.json` contract is
preserved), so a fleet may migrate to v4 **incrementally, per repo** — you do not have to flip every
repo's NF line at once. (The Angular *major* still moves in lockstep; the NF *line* may lag per repo.)

**All-or-nothing, and check the current floor.** A major Angular bump cannot be applied to a *subset* of
the federation — every repo that shares the singleton must move together; there is no "upgrade 3 of 14
remotes" for a major. And if the fleet's **current** Angular majors already differ (the inventory shows
`@angular/core` varying across repos), that is a **pre-existing** lockstep violation — reconcile the
fleet onto one major *before* targeting a higher one. The reconciled manifest is a **precondition** for
the host's lockstep confirmation above.

### Assisted discovery (bundled script)

`scripts/federation-discovery.sh` automates steps 1–3 from a GitLab namespace — **read-only, no
cloning** (it reads `package.json` + `federation.config.*` through the GitLab raw-file API). Point it
at the group(s) holding the federated apps, plus any hosts that live *outside* those groups:

```bash
GITLAB_HOST=gitlab.example.com \
TOKEN_FILE=~/.your-git-token \
GITLAB_GROUPS="your-group/frontend-remotes" \  # NB: GITLAB_GROUPS, not GROUPS (reserved bash builtin)
EXTRA_REPOS="your-group/app-shell" \           # host often lives OUTSIDE the remotes' group
NG_TARGET=22 \                                 # optional: pre-fill suggested_pin per singleton from npm
OUT=AI/federation \
scripts/federation-discovery.sh
```

It writes `federation-inventory.tsv` (per repo: line v3/v4, role, framework versions, adapter, and a
`shared` column showing how the set was derived — e.g. `share(17)`, `shareAll(N)`, or `shortlist(10)`)
and `federation-singletons.json` — the reconciliation manifest over the **full parsed shared set** (so
`@platform/*`, `@ngx-translate/*` etc. are included, not just the framework): per singleton, the
`observed` version in each repo, a `drift` flag, a `suggested_pin`, and the final `pin`. Passing
`NG_TARGET=<major>` queries npm to pre-fill `suggested_pin` (`@angular/*` → exact latest patch; `rxjs` /
`zone.js` → Angular's declared peer range; `tslib` → Angular's dep range; other singletons left blank).
You then set the final `pin` to **one exact version, identical across all repos**. It **proposes; it does
not pin** — the pin is a human call (and for `rxjs`/`zone.js` you must narrow Angular's range to one
concrete version).

Caveats (learned running it against real repos):
- **Scan ONE federation per run.** Drift is only meaningful within a single federation (a host + *its own*
  remotes that share a runtime). Mixing unrelated federations in one scan (e.g. an app-shell fleet + a
  separate portal fleet) reports "drift" between repos that never share a host — meaningless. One run =
  one host + its remotes.
- **The host is usually NOT in the remotes' group.** Listing one group finds the remotes; pass the host
  repo via `EXTRA_REPOS` (or a second `GITLAB_GROUPS` entry). One namespace ≠ the full federation topology.
- **Host detection runs only for `EXTRA_REPOS`.** To stay fast on large fleets, group members are labeled
  `remote` by default (no blind manifest probing); a host is detected only when passed via `EXTRA_REPOS`
  or when its root `federation.config` declares `remotes`/`initFederation`. Always pass the host via
  `EXTRA_REPOS`.
- **Line + shared-set detection need the config at repo root.** Repos whose `federation.config.*` sits in
  a subfolder (or an Nx `project.json`) show line `-` and fall back to the framework `shortlist` for the
  shared set — confirm in the supervised step rather than trusting the blank/shortlist.
- **Drift is common in practice.** A real run across `your-group/frontend-remotes` (14 remotes, all Angular
  19.1.6) still showed `rxjs` split `6.5.4` vs `7.8.2` (an RxJS 6-vs-7 major gap), plus mixed `tslib`
  and `zone.js` — exactly the singletons to pin before any upgrade.
- **It scans the default branch.** A repo mid-migration to NF on a feature branch won't show on
  `master` — pass it as `path@ref` in `EXTRA_REPOS`, e.g.
  `your-group/portal-app@feat/native-federation-migration`.
- **Module Federation repos are skipped with a `note:`.** A repo using `@your-org/module-federation` /
  `@angular-architects/module-federation` (webpack MF) is not Native Federation — the script logs a
  `note:` to stderr and excludes it. Those are out of scope (hard-stop in Phase 0B).
- **Assumes the Angular app is at repo ROOT.** It reads root `package.json` / `federation.config.*`. A
  repo whose app lives in a subfolder (workspace/monorepo, nested app) won't be detected — handle those
  manually. Two branches of the *same* repo (both NF) also collide by name in the manifest — scan one
  branch per repo.

## Adapter package selection — target major AND current NF line

The right package depends on the **target Angular major** and on the project's **current NF line**
(v3 vs v4 — detect it: a `federation.config.js` / `require`-style config resolving `@softarc/*@3.x`
⇒ **v3**; a `federation.config.mjs` / `export default` config resolving `@softarc/*@4.x` ⇒ **v4**).

| Target Angular | Adapter package | NF line | Config format |
|----------------|-----------------|---------|---------------|
| ≤ 19 | `@angular-architects/native-federation` (Angular-major-aligned) | v3 (`@softarc/native-federation@3.x`) | `federation.config.js` (CommonJS) |
| 20 / 21 | `@angular-architects/native-federation-v4` (recommended) — or an existing v3 install may remain | v4 (recommended) / v3 (retained) | `.mjs` (v4) · `.js` (v3) |
| 22+ | `@angular-architects/native-federation@22.x` | v4 (`@softarc/native-federation@4.x`), mandatory | `federation.config.mjs` (ESM) |

### The v4 decision on Angular 20/21 — and it does NOT require Angular 22

v4 is **mandatory only at Angular 22+**. On Angular **20/21** the vendor-recommended adapter is
`@angular-architects/native-federation-v4` — and the key point you should surface: it runs the v4 line
**without upgrading Angular to 22** (a backport published under a distinct name so it coexists with an
existing v3 install). The v3 line still supports Angular ≤21, so an app already on v3 can remain there
short-term as the lower-churn option. So the decision hinges on the **current** line:

- **Currently on v4** (`-v4` or `@22.x`, `.mjs` config) → just bump the v4 package for the target
  (`-v4` on 20/21, `@22.x` on 22). **No config migration.**
- **Currently on v3, target 20/21** → choose: adopt `-v4` now (recommended forward path — run the
  v3→v4 checklist below) **or** defer and stay on v3 (lower churn, no config change). Genuine,
  non-mechanical decision — **ask the user**, and make clear v4 here does **not** force an Angular-22 jump.
- **Currently on v3, target 22+** → v4 is unavoidable; run the v3→v4 checklist.

Other notes:
- SSR + Incremental Hydration is supported from adapter **v18** onward; I18N from **v19.0.13**.
- Do **not** assume version numbers — resolve the actual package/versions via npm:
  `npm view @angular-architects/native-federation versions --json` and
  `npm view @angular-architects/native-federation-v4 versions --json`.
- **Multi-major jump** (e.g. v19→v22): each per-major step (SKILL.md Phase 0A) targets that step's
  Angular; the v3→v4 migration lands at whichever step first moves onto the v4 line (at latest, the
  step to 22 — `ng update @angular-architects/native-federation` transitions off `-v4` there).
- **Nx workspaces**: the adapter API is identical, but config lives in `project.json` targets/executors
  (not `angular.json`), the shared config uses `withNativeFederation`, and the builder migration is
  `ng g @angular-architects/native-federation:appbuilder`. Detect via `nx.json` + per-app `project.json`.

## Upgrade procedure (Phase 3)

Native Federation ships `ng update` schematics that migrate config + server files automatically — run
them; don't hand-edit first. Slot this **right after Angular core + CLI** (Group 2), because the
adapter rides Angular's `ApplicationBuilder` and must match the just-installed Angular.

```bash
# v4 (Angular 20+) wipes stale caches first — v4 changes the emitted module format.
rm -rf dist .angular node_modules/.cache

# Use the correct package NAME for the target major (see table above).
npx ng update @angular-architects/native-federation@{ADAPTER_TARGET} --allow-dirty --force
# ...or, for Angular 20/21:
# npx ng update @angular-architects/native-federation-v4@{ADAPTER_TARGET} --allow-dirty --force
```

If `ng update` for the adapter is unavailable for the step, bump directly
(`{pkg-manager} add -D @angular-architects/native-federation@{target}`) and apply the v3→v4 checklist
below by hand. Then `{install-command}` and run the Phase 3 build gate.

## v3 → v4 breaking-change checklist (crossing into Angular 20+)

Applies **only when the step actually lands on the v4 line** — i.e. target **Angular 22+**
(mandatory), or an **explicit opt-in to v4 on Angular 20/21** (the `-v4` package). It does **not**
apply to a plain Angular 20/21 bump that stays on the v3 line — that keeps `federation.config.js` and
needs none of the below. When it does apply, audit each item in Phase 3B even if the schematic claims
to have handled it:

1. **CommonJS → ESM everywhere.** Rename `federation.config.js` → `federation.config.mjs`; replace
   `require('@softarc/native-federation/config')` with `import`, and `module.exports` with
   `export default`. Do **not** add `"type": "module"` to `package.json` — the `.mjs` extension is
   enough.
2. **Core packages to v4.** `@softarc/native-federation`, `@softarc/native-federation-runtime` →
   `~4.0.0` — and, for an **SSR host**, `@softarc/native-federation-node` → its v4-compatible release.
   (Orchestrator below is optional.)
3. **`shareAll()` overrides merge inline.** v4 wants per-package overrides passed into `shareAll()`
   rather than chained separate `share()` calls — reconcile the shared-deps config.
4. **`features` block** (optional): `denseChunking: true` is v4; note `ignoreUnusedDeps: true` already
   exists on late v3 (seen in real 19.0.x configs) — its presence does NOT indicate the v4 line.
5. **Orchestrator runtime is opt-in and CLIENT-SIDE ONLY.** `@softarc/native-federation-orchestrator`
   adds semver-range resolution, persistent caching, share scopes — but it does not run remote modules
   during SSR. **If the app uses SSR, keep the Classic Runtime on the SSR path.** Do not switch a
   server-rendered host to the Orchestrator as part of an upgrade unless the user asks.
6. **Cache wipe before first v4 build** (the `rm -rf` above) — stale `.angular`/`dist` caches produce
   spurious build failures on the v3→v4 boundary.

## Angular 20 build layout — config files must move to repo ROOT (v3 adapter)

On the **v3 adapter at Angular 20** (`@angular-architects/native-federation@20.x` + `@softarc/native-federation@3.5.x`)
the builder derives paths from the **tsConfig directory** — so a `src/`-nested layout breaks the
production build with three *sequential* errors (each only visible after fixing the previous one):

1. `FsPath: <repo>/src/src/main.ts does not exist` — the builder computes
   `entryPoint = path.join(path.dirname(options.tsConfig), 'src/main.ts')` (hardcoded, no override), so a
   tsConfig under `src/` yields the bogus `src/src/main.ts`. Surfaced via the `ignoreUnusedDeps` feature
   calling `@softarc/sheriff-core`'s `getProjectData`.
2. `Expected <repo>/federation.config.js` — `inferConfigPath(tsConfig)` expects `federation.config.js` as a
   **sibling of the tsConfig**.
3. `invalid path mapping detected: @angular/*: ../node_modules/@angular/*` — once the tsConfig moves to
   root, a base-tsconfig `paths: {"@angular/*": ["../node_modules/@angular/*"]}` (calibrated for the old
   `src/` depth) now resolves outside the repo.

**Requirement: for NF v20, `tsconfig.app.json` and `federation.config.js` must both live at the workspace
root.** Fix (apply identically across host + all remotes — they share the layout):

- `git mv src/tsconfig.app.json tsconfig.app.json` — fix `extends`/`outDir` to `./`, `files` to `src/*.ts`,
  and set `baseUrl: "src"` to preserve `@angular/*` resolution semantics.
- `git mv src/federation.config.js federation.config.js`.
- `angular.json`: point the esbuild target's `tsConfig` at `tsconfig.app.json` (was `src/tsconfig.app.json`).
- Delete the `@angular/*` path mapping from the base `tsconfig.json` (Angular resolves via `node_modules`).
- Also flip tsconfig `moduleResolution` `node` → `bundler` if not already (Angular 19+).

This is blocker-class: none of the three errors is in the Angular update guide, and a hands-off run would
hit the "unknown error → STOP" circuit breaker here. Error signatures are also in `references/build-fix-patterns.md`.

## SSR with Native Federation (Phase 4)

Federated SSR initializes federation on the **server** before Angular renders. The file layout evolved:

- **Adapter v18–v19**: project has both `server.ts` and `bootstrap.server.ts`. `server.ts` calls
  `initNodeFederation(...)` (import maps on the server) before delegating to the Angular bootstrap.
- **Adapter v20+**: the build generates **`fstart.mjs`** ("federation start") in the server output. It
  initializes federation and then delegates to the CLI-generated `server.mjs`. On migrating to v20 you
  can delete `server.ts` and rename `bootstrap.server.ts` → `server.ts`.

**Run the SSR server with `node fstart.mjs`, NOT `node server.mjs`** (v20+). Starting `server.mjs`
directly skips federation init and remotes won't resolve server-side.

- **Discover the actual output path** — `fstart.mjs`/`server.mjs` live under the project's
  `outputPath` (commonly `dist/<app>/server/`, not the bare `dist/server/` the plain-SSR reference
  assumes). Read it from `angular.json`; don't hardcode.
- Keep the **Classic Runtime** for SSR (the Orchestrator is client-only — see v4 checklist item 5).
- Fold this into the Phase 4 SSR boot check: prefer the project's SSR dev script; otherwise start
  `node <outputPath>/server/fstart.mjs` (v20+) or `.../server.mjs` (v18–19), then assert HTTP 200 +
  `ng-version` + a clean server log, same as the base SSR check.
- The custom `server.ts` concerns (CSP/nonce, redirects, Prometheus, Morgan) still apply — but
  with `fstart.mjs` in front, confirm the federation-start wrapper preserves them (the CLI-generated
  `server.mjs` it delegates to is where the custom middleware lives).
- **Prerender / SSG needs remotes at BUILD time.** If the host uses `outputMode: static` or route
  prerendering, remote `remoteEntry.json`s must be reachable *during the build* (the manifest must
  point at published/running remotes). A federated build can fail at the prerender step with the
  remotes unreachable — point the manifest at reachable remotes for the build, or exclude federated
  routes from prerender. This is a build-gate failure mode the plain-SSR flow never hits.

## Import maps, es-module-shims & CSP (internal nonce interaction)

Native Federation loads remotes via **import maps**, polyfilled by **es-module-shims** — configured by
a `<script type="esms-options">` block plus an es-module-shims `<script>` in `index.html`. This
intersects with a strict CSP + per-request nonce (see `references/ssr-migration-patterns.md`),
so an Angular/adapter upgrade can break remote loading **without any build error**:

- **CSP must allow the federation origins.** `script-src` (and, for server/fetch, `connect-src`) has to
  include every remote's origin plus the import-map / es-module-shims scripts. If a remote changed
  origin or CSP was tightened during the upgrade, remotes fail with a CSP violation — catch it via the
  browser console in the runtime check, not the build.
- **Nonce alignment.** es-module-shims takes its nonce from the first script on the page or the `nonce`
  field in `esms-options`. The server-side `injectNonceIntoScripts` must cover the import-map and
  es-module-shims script tags, and the `esms-options` nonce must match Angular's `CSP_NONCE`. An upgrade
  that touches the nonce-injection regex or bumps es-module-shims can silently break this.
- **es-module-shims version.** Pinned in `index.html` and/or `package.json`. A major NF bump can require
  a newer es-module-shims; if remotes stop loading with an import-map/shim error after the bump, check
  and bump it.

## Runtime verification (Phase 3B / Phase 4)

`ng serve` for a federated app only wires remotes **client-side**; a host served alone cannot render
its remotes server-side (needs fallback components), and remotes whose URLs point at other
environments won't be reachable. Adapt the runtime check:

- **Remote**: after build/serve, verify the federation entry is served —
  `curl -fsS http://localhost:{PORT}/remoteEntry.json` returns JSON (the exposed-modules manifest).
- **Host**: keep the HTTP 200 + `ng-version` check on the shell, but **document** that remote-load
  failures are lazy/client-side and won't surface in this check. Do not treat a shell-only 200 as proof
  the federation works end-to-end — that requires the lockstep-upgraded remotes running.

## Deployment (Phase 9 / PM2 / checklist)

- **SSR entry point** for PM2/`node` is **`fstart.mjs`** (adapter v20+), not `server.mjs`. Update the
  PM2 `script` field / start command accordingly and verify the path resolves after build.
- **`federation.manifest.json`** carries remote URLs and is environment-specific — confirm the correct
  manifest ships per environment (stage/preprod/prod) so the host loads the right remote builds.
- **`remoteEntry.json`** for each remote must be published and served at its configured URL.
- **Shared-dependency alignment**: singleton versions (Angular et al.) must match across host + remotes
  — restate the lockstep requirement in the deployment checklist.

## Third-party dependencies & breaking changes

Two federation-specific angles on top of the normal Phase 8B third-party sweep:

1. **The adapter is version-locked to the Angular major** (like CDK/Material) — treat it as a required
   lockstep bump, not a loose "latest that supports v{TO}" Group-5 bump. Use the package-name table
   above; the wrong package name (`native-federation` vs `native-federation-v4`) is itself a break.
2. **Shared/singleton third-party libs are frozen to the reconciled pin — Phase 8B must NOT bump them.**
   Any `singleton: true` lib (state store, design-system package) must resolve to the **same exact**
   version across host + all remotes (see "Cross-repo singleton reconciliation" above); under
   `strictVersion` a mismatch throws. Phase 8B sweeps only **non-singleton** third-party libs — a
   singleton needing a different version is a cross-repo reconciliation decision, not a unilateral bump.
