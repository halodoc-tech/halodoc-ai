---
name: web-dep-policy
description: Onboards a web app to the central dependency version policy (@your-org/pnpm-plugin-dep-version-policy, a pnpm 10 config dependency), and updates an already-onboarded app to a newer policy. Runs an audit (repo versions vs. the latest policy from the private registry), FLAGS MAJOR bumps before touching anything, migrates pnpm 8->10 with a zero-drift lockfile conversion, wires or updates catalog: pointers, repins the config dependency, and fixes known breaking changes (eslint 10, husky 9, pdfjs-dist 5, ngx-* majors), validating against the CI Dependency Policy Gate. Use for both a first onboard and an already-onboarded repo: onboard to the central version policy / dependency governance / version catalog / governed dependencies; repin, bump, or update the policy pin after a new release; a STALE CI gate failure; check versions against the centralized/master config; catalog: pointers, version drift, or pnpm-plugin-dep-version-policy; or fix a policy bump's breaking changes.
---

# Onboard a web app to the central dependency version policy — and keep it current

> Identifiers below (the package scope `@your-org/…`, the registry host, repo
> paths, CI helper names) are placeholders — swap them for your organization's.

The org governs shared dependency versions fleet-wide through one package:
`@your-org/pnpm-plugin-dep-version-policy` (source: `your-org/dependency-version-policy` →
`projects/pnpm-plugin-dep-version-policy`, published ONLY via that repo's release
pipeline to the private registry `https://npm.your-org.internal/`). Consuming repos
declare it as a **pnpm 10 config dependency**; its auto-loaded pnpmfile injects
version **catalogs** (a `default` catalog plus per-Angular-cluster catalogs, one per
Angular major, named `ng<major>`), and apps replace hardcoded versions with `"catalog:"` pointers.
A CI **Dependency Policy Gate** fails builds whose policy pin goes stale.

Reference onboardings (what "done" looks like):
- a micro-app onboarding (the standard pnpm CI pipeline; governs the full eslint
  toolchain + husky)
- the policy repo itself (what a policy-content change looks like: catalog entries
  + the spec assertions that pin the reasoning)
- a website app onboarding (the Docker CI pipeline, includes a pnpm 8→10 migration)

Work on a feature branch (`feat/dep-policy-onboard` for onboarding,
`feat/dep-policy-update` for pin updates). Never publish the policy package from a
laptop; policy content changes are a separate MR to `your-org/dependency-version-policy`
targeting `stage-release`.

## Mode selection — run the audit first, it tells you which flow applies

Run `node <skill-dir>/scripts/version-audit.mjs` from the repo root before
anything else. It always fetches the **newest published policy** from the registry
(rc channel while no stable exists, `latest` once one does) and prints a
`mode:` line:

- **`mode: ONBOARD`** — no policy config dependency yet → follow Phases 0–5.
- **`mode: UPDATE — PIN STALE`** — the repo is onboarded but pins an older
  policy version → follow the **Update flow** below. The audit also prints the
  exact governed-version changes between the pinned and newest policy, so you
  know what the update pulls in before touching anything.
- Whatever the mode, rows labeled **`MISMATCH (onboarded)`** need immediate
  attention: the dep is declared `catalog:` but its LOCKED version differs from
  the policy. Check the cheap cause FIRST: the lockfile simply has not been
  regenerated since the pin or the pointer changed — run
  `pnpm install --lockfile-only` and re-audit before investigating anything else.
  Otherwise it is a repo-local catalog entry shadowing the central one
  (`catalogMode: prefer/strict` auto-creates these on `pnpm add`, notably for
  cluster-governed deps it can't find in the default catalog) or a wrong
  catalog name. Fix: delete the local catalog entry / correct the pointer
  (`catalog:<cluster>` for cluster deps), reinstall, re-audit. Do NOT enable
  `catalogMode` on governed repos — stay on the default `manual`.
- **`mode: UPDATE — pin is CURRENT`** — nothing to do (unless the developer
  wants to convert more deps to `catalog:` pointers, which is Phases 1→5 for
  just those deps).

## Update flow — already-onboarded repo, stale pin

This is the routine "a new policy version was published" path — also exactly
what a CI gate failure of the form `STALE — repo pins X but the newest is
Y` prescribes.

1. Review the audit's "policy changes between <pinned> and <newest>" list.
   Entries marked `<-- referenced by this repo via catalog:` change this repo's
   installed versions on update. Treat any **MAJOR** among those exactly like
   an onboarding-time major: remediate it, or record an `exceptionCatalogs`
   entry (policy MR) if this repo genuinely needs a different version.
   Reverting the dep to a literal version is NOT an option — the local-pin guard
   fails the install on it (see Phase 1). Unreferenced changes are informational.

   **ADDED entries need conversion, not just a pin bump.** A policy release that
   newly governs a dep this repo declares literally turns that literal into a hard
   install failure. Convert every newly-governed dep to `catalog:` in the SAME
   commit as the pin bump. Corollary for policy owners: expanding the governed set
   is a breaking change for every onboarded repo declaring those deps, so the
   policy MR and the consuming conversions have to land together.

   **REMOVED entries need conversion too — back to a literal.** The mirror case: a
   policy release that DROPS a dep from the catalog (the audit prints it as
   `REMOVED <-- referenced by this repo via catalog:`) makes a bare pin bump fail with
   `ERR_PNPM_CATALOG_ENTRY_NOT_FOUND_FOR_SPEC`. Convert that dep from `catalog:` back
   to a literal — pinned at the version the catalog last resolved to, so it's
   version-neutral — in the SAME commit as the pin bump. The local-pin guard does NOT
   object here (it only rejects literals for deps the policy STILL governs).
2. Bump the pin with pnpm's own command, using the EXPLICIT version the audit
   printed as `policy:` — it resolves, hash-verifies, and writes the exact
   `version+sha512` into pnpm-workspace.yaml in one shot:
   ```bash
   npx -y pnpm@10 add --config @your-org/pnpm-plugin-dep-version-policy@<version-from-audit>
   ```
   **BEFORE running it — normalise the pin location.** If package.json carries a
   `pnpm` section (a CVE override is the usual reason), move that WHOLE block to
   pnpm-workspace.yaml first. pnpm keeps settings where the repo already keeps
   them, so with a `pnpm` section present this command writes the pin into
   `package.json#pnpm.configDependencies` and leaves pnpm-workspace.yaml alone.
   Two verified consequences, both silent:
     - **First onboard** — the repo IS governed from there (pnpm honours it), but
       the CI gate reports `SKIP: repo is not onboarded` and checks nothing.
       It fails OPEN: no staleness check, no integrity check.
     - **Repin of a repo already pinned in pnpm-workspace.yaml** — the new version
       is written to package.json while the OLD one stays in the workspace file,
       and pnpm resolves the WORKSPACE one. The repin does nothing while printing
       `Installed config dependencies: …@<new version>`.
   Moving the block is free: an identical override in package.json vs
   pnpm-workspace.yaml produces a byte-identical lockfile, override still applied
   transitively. Every `pnpm.*` key has a top-level home there — `overrides`,
   `packageExtensions`, `peerDependencyRules`, `patchedDependencies`,
   `onlyBuiltDependencies`, `allowedDeprecatedVersions`, `neverBuiltDependencies`.
   Known cases needing this: a shared commons library (`form-data`), an MFE
   (luxon), a website app.
   **AFTER running it**, confirm the pin landed in pnpm-workspace.yaml and that
   package.json has no `configDependencies`. Re-running `version-audit.mjs` is the
   cheapest check — it prints `pinLocation` and flags a conflict between the two.
   (Editing the version+sha512 line by hand is equivalent and always safe.)
   Also commit pnpm-lock.yaml when it changes — a policy release that ships new
   hook code changes the lockfile's pnpmfileChecksum even if no versions moved.
   Why the explicit version and not a dist-tag: the audit already resolved the
   correct channel (stable `latest` when one exists; `rc` only while no stable
   has been published). A bare/`@latest` add is only safe once a stable exists —
   during the bootstrap era `latest` points at a historical rc and would pin an
   OLD policy (the gate would catch it as STALE, but don't rely on that).
3. Sync the lockfile and validate:
   ```bash
   npx -y pnpm@10 install --lockfile-only
   npx -y pnpm@10 install --frozen-lockfile
   ```
   The hook log must show the injected catalog counts. If the new policy moved
   none of this repo's referenced entries and the hook code is unchanged, the
   lockfile legitimately stays untouched — a one-line pin diff is a valid
   outcome, don't force churn.
4. Verify installed versions for every `catalog:`-pointed dep (read
   `node_modules/<dep>/package.json`), run the drift check
   (`python3 <skill-dir>/scripts/lockfile-drift-check.py`) — only the deps the
   new policy moved may change — and run lint/tests if any runtime dep moved.
   Remediate breaking changes per Phase 5 / `references/breaking-changes.md`. Also
   confirm the repo's `AGENTS.md` carries the centrally-governed note (Phase 3
   step 5) — add it if an earlier onboarding predated it.
5. Commit (message: what policy version, what it pulls in), push, and watch
   the CI build: the Dependency Policy Gate must print `PASS` on the new
   pin. A red gate right after a push usually means yet another policy version
   published in between — re-run the audit and repeat.

## Phase 0 — Preflight (ONBOARD mode)

1. Node ≥ 20 available; private registry reachable (VPN): `curl -s -o /dev/null -w '%{http_code}' https://npm.your-org.internal/` → 200.
2. Identify the repo's package manager era from `pnpm-lock.yaml` line 1:
   `lockfileVersion: '6.0'` = pnpm 8 (needs the two-step conversion in Phase 2);
   `'9.0'` = pnpm 9/10 (convert step not needed).
3. Read the CI config: note `job_type`. The gate + pnpm provisioning are in
   the standard pnpm and Docker CI pipelines. Any other job_type still enforces
   at install time, but flag to the user that the gate stage needs porting to that
   pipeline (pattern: a thin stage calling `ci.dependencyPolicyGate()`).

## Phase 1 — Interpret the version-bump audit (ONBOARD mode)

The audit (already run in Mode selection) compares every governed dependency
the repo declares against the newest policy catalogs and classifies each as
SAME / PATCH / MINOR / **MAJOR**, plus the repo's cluster situation. Decide,
dep by dep:

- **SAME / PATCH / MINOR** → convert to a `catalog:` pointer now. These are the
  low-risk wins; minor runtime bumps get validated by the repo's own test suite
  in CI.
- **MAJOR** → STOP and surface it to the developer explicitly (list the dep,
  current → policy version, and what depends on it).

  **There is no per-dep defer.** Older guidance said un-pointered deps are
  "simply not governed yet" — that is FALSE against the shipped hook. Once the
  config dependency is pinned, `localPinViolations` throws for ANY governed dep
  the repo declares with a literal version, and `localPinMode` defaults to
  `error`. The install fails outright, before the CI gate stage runs.
  `ORG_POLICY_LOCAL_PIN=warn` is local-only ("the CI gate reads no env"), so
  it unblocks your laptop and nothing else. Onboarding is therefore all-or-nothing
  across the governed deps a repo declares. Three real options:
  1. **Remediate**: convert the pointer AND fix the breaking changes in the same
     branch — follow Phase 5 with `references/breaking-changes.md`.
  2. **Don't onboard yet**: leave the repo unpinned entirely. No config
     dependency = no hook = nothing governed. This is the only way to postpone a
     major, and it postpones the whole repo, not one dep.
  3. **exceptionCatalogs**: a sanctioned per-repo divergence pinning that dep to
     a different version, then point at `catalog:<name>`. This is policy content,
     so it is a separate MR to `your-org/dependency-version-policy`
     targeting `stage-release` — it blocks the onboarding until it publishes.
- **Cluster deps** (the audit marks them): a repo may only reference the cluster
  catalog for its own Angular major — **derived from `@angular/core`** (Angular `<major>`
  → `catalog:ng<major>`) — and the install-time guard hard-fails on a mismatch. There is
  NO cluster registry anywhere: no repo list to join, no policy MR to raise. The
  guard computes `ng${currentAngularMajor()}` and compares; the only allowlist in
  the policy is for `exceptionCatalogs`. Verified on an unregistered Angular-major
  repo: pointing at `catalog:ng<major>` logs `coherent — Angular <major> (ng<major>), references
  match` and installs green. The one thing that CAN block you is the policy not
  carrying an entry for that dep in your cluster — then pnpm fails with
  `ERR_PNPM_CATALOG_ENTRY_NOT_FOUND_FOR_SPEC` and it needs a policy MR to add it.
  Global-only onboarding is always fine.

## Phase 2 — pnpm 8 → 10 lockfile conversion (only if lockfileVersion 6.0)

pnpm 10 CANNOT faithfully convert a v6 lockfile — it re-resolves hundreds of
ranges (observed: ~200 packages drifted on a large website repo). pnpm 9
converts v6 → v9 with **zero resolution changes**. So, as its own commit, BEFORE
adding `engines`/`packageManager` (their floor blocks pnpm 9):

```bash
npx -y pnpm@9 install --lockfile-only
python3 <skill-dir>/scripts/lockfile-drift-check.py   # must print: 0 changes
git add pnpm-lock.yaml
git commit -m "chore: convert pnpm-lock.yaml to lockfileVersion 9.0 (pnpm 9/10 format)"
```

If the drift check is not zero, stop and investigate — do not proceed on a
drifted conversion.

## Phase 3 — Apply the onboarding (one commit)

1. **package.json**
   - `"packageManager": "pnpm@10.x.y"` — the exact toolchain; CI derives its
     per-build pnpm provisioning from this field (no corepack needed on agents).
   - `"engines": { "pnpm": ">=10.4.0" }` — feature floor for configDependencies;
     older pnpm gets a clear refusal instead of a confusing failure.
   - Convert each approved dep's version to `"catalog:"` (global) or
     `"catalog:<cluster>"` (cluster deps — the cluster must match the repo's
     `@angular/core` major).
2. **pnpm-workspace.yaml** — let pnpm create and pin it (resolves, verifies,
   and writes the exact `version+sha512` automatically; the pin the audit
   printed is the same value if you prefer to paste it by hand). Use the
   explicit version the audit resolved — it is channel-aware (stable `latest`
   when one exists, `rc` only during bootstrap), so the command stays correct
   before and after the policy's stable GA:
   ```bash
   npx -y pnpm@10 add --config @your-org/pnpm-plugin-dep-version-policy@<version-from-audit>
   ```
   If package.json carries a `pnpm` section (`overrides` etc.), **move the whole
   block here BEFORE running the command** — do not leave it. With that section
   present, pnpm writes the pin into `package.json#pnpm.configDependencies`
   instead, and the CI gate then reports `SKIP: repo is not onboarded` while
   the policy is silently active — it fails OPEN. See the same note in the UPDATE
   flow above for the verified failure modes; the move is lockfile-neutral.
3. **CI config** — no change for the standard pnpm/Docker pipelines (the gate is in
   the default shared library). For any other job_type, port the gate stage (Phase 0.3).
4. **Lockfile**:
   ```bash
   npx -y pnpm@10 install --lockfile-only
   ```
   Heads-up: pnpm 10 eagerly resolves configDependencies on ANY pnpm command in
   the workspace — if this hangs or 404s, the registry isn't set for the
   `@your-org` scope in `~/.npmrc` (it must point at the private registry before
   the first pnpm invocation).
5. **AGENTS.md** — record the governance context so a future agent (or human) does
   not literalise a `catalog:` pin. The repo-root `AGENTS.md` is the standing brief
   for anyone working in the repo. **If it already carries a centrally-governed /
   dependency-policy section, leave it** (idempotent — never duplicate); otherwise
   create `AGENTS.md`, or append to the existing one, with:

   ```markdown
   ## Dependency versions — centrally governed

   This repo is onboarded to the central dependency version policy
   (`@your-org/pnpm-plugin-dep-version-policy`, a pnpm config dependency pinned in
   `pnpm-workspace.yaml`). Governed dependencies are declared in `package.json` as
   `catalog:` (global) or `catalog:<cluster>` (Angular-cluster) pointers, **not**
   literal versions — the install-time guard hard-fails a literal for a governed dep.

   - Do NOT change a governed dep to a literal version, and do NOT hand-edit its
     version here — governed versions live in the policy repo
     (`your-org/dependency-version-policy`), not this repo.
   - To adopt a newer policy (repin, or after a STALE CI gate failure), use the
     `web-dep-policy` skill — it bumps the pin and refreshes the `catalog:` pointers
     in one commit.
   - The CI Dependency Policy Gate enforces the pin is current + integrity-valid.
   ```

## Phase 4 — Validate locally, then in CI

Local (all four must pass before pushing):
1. `npx -y pnpm@10 install --frozen-lockfile` — green, and the hook log
   line appears: `[versions] injected catalogs — default: N; ng<major>: N; …`.
2. Installed versions match policy: read `node_modules/<dep>/package.json`
   `version` for every converted dep (some packages block `require('<dep>/package.json')`
   via exports — read the file, don't require it).
3. `python3 <skill-dir>/scripts/lockfile-drift-check.py` vs the pre-onboarding
   commit — the ONLY version changes must be the governed bumps you approved.
   Pure REMOVALS of orphaned duplicates are expected and fine (pnpm 10's peer
   resolution stops auto-installing second copies for stale peers — e.g. an
   entire webpack@4 subtree can vanish, correctly).
4. Repo lint + (if fast enough) tests. If lint uses eslint and eslint is being
   governed, expect the `@typescript-eslint` coupling — see breaking-changes.md.

CI:
1. Push the branch; the multibranch job indexes it (a minute or two).
2. Watch the build: `Dependency Policy Gate` stage must print
   `pinned: <ver> | latest: … | rc: …` then `PASS: policy pin valid for its
   channel, integrity verified.` — followed by
   `provisioning pnpm@10.x.y (from package.json packageManager)`, the catalogs
   hook log, and green tests. Deploy stages skip on feature branches — expected.
3. If the gate FAILS with STALE: a newer policy was published since you ran the
   audit — re-run the audit, re-pin, regenerate the lockfile, push again. That
   failure mode is the gate working, not a bug.
4. Raise a **Draft** MR using `references/mr-template.md`. Keep the diff to
   onboarding only — reviewers push back hard on unrelated resolution churn.

## Phase 5 — Breaking-change remediation (MAJOR bumps the developer approved)

One dep per commit, build + test after each. For every approved major:

1. Read `references/breaking-changes.md` first — it has verified recipes for
   the governed set (eslint 10's @typescript-eslint coupling, husky 9 hook
   format, pdfjs-dist 5 worker/ESM changes, ngx-* Angular-major locks,
   ua-parser-js 2, @ngx-translate 18…). Known pairs come with exact fixes.
2. For majors not in the reference: `npm view <dep> repository.url`, fetch the
   changelog/release notes between the current and target majors, then grep the
   codebase for the package's imports and each documented breaking API. Fix
   call sites, run the build and the affected tests, iterate on errors.
3. Transitive/peer couplings hide in the lockfile, not package.json — if a
   catalog bump makes a tool crash with something like
   `Class extends value undefined`, a transitive companion is too old for the
   new major. Fix it with a **surgical lockfile re-peer** (see
   breaking-changes.md § eslint) — do NOT run a bare `pnpm dedupe`, it
   garbage-collects unrelated duplicates and bloats the review diff badly.
4. If a major can't be fixed within the session, reverting that one dep to a
   literal version does NOT work — the local-pin guard fails the install. Either
   land an `exceptionCatalogs` entry for it (policy MR to `stage-release`, which
   blocks this branch until it publishes), or park the whole onboarding by
   dropping the config dependency until the major can be done. Say which you did
   in the MR; do not leave a literal version next to a live pin.

## Safety rails

- Policy content (versions, exceptions) changes ONLY via a `dependency-version-policy`
  MR to `stage-release` — the pipeline publishes; never `npm publish` by hand.
- Two same-cluster apps needing different versions of a governed dep is an
  `exceptionCatalogs` entry in policy.json (allowlisted per repo, guard-enforced)
  — not a reason to skip governance.
- The rc channel is the fleet source while no stable exists (`latest` may point
  at a historical rc — the gate's bootstrap mode handles it; don't "fix" tags).

## See also

- `angular-upgrade` skill — the Angular framework migration (code side). On a **major** it hands the
  cluster repoint back here: the repo's cluster is derived from `@angular/core`, so crossing a major
  means repointing `catalog:ng<old>` → `catalog:ng<new>` and repinning (this skill).
- `your-org/dependency-version-policy` → `docs/angular-major-upgrade.md` — the policy-side
  playbook for standing up / retiring an `ngNN` cluster catalog (a prerequisite when a repo moves to
  an Angular major the fleet has not governed yet).
