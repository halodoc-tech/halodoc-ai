---
name: angular-upgrade
description: >
  Automates Angular version upgrades safely with SSR awareness, internal package handling, and
  iterative error-driven fixes, as a guided phased workflow that pauses to ask at real decision points.
  Use when: "upgrade Angular", "migrate to Angular X", "ng update", "update Angular version",
  "angular migration", "move to Angular X" — and "upgrade dependencies", "update framework version",
  "bring this repo up to date" only when angular.json or @angular/core is present.
  Handles common patterns: @your-org/*, @web-shared/*, @design-system/*, @platform/* packages, Express 5 SSR, PM2 configs,
  CSP nonce injection, and Native Federation hosts/remotes (@angular-architects/native-federation).
  Also triggers on "/angular-upgrade", "native federation upgrade", "micro-frontend upgrade".
  Re-enter post-deploy (Phase 10) on "verify the deploy", "post-deploy verification",
  "remotes broken after deploy", "singleton skew", "stale remoteEntry".
  Does not handle webpack Module Federation (hard-stops); not a CI/unattended job.
---

# Angular Upgrade Skill

Orchestrates Angular version upgrades through a phased, iterative workflow with built-in
circuit breakers and org-specific knowledge.

## Operating Mode

This skill is interactive — it works autonomously on mechanical changes but can pause to ask
the user when it hits a genuine decision point or an unresolvable blocker.

- **Prefer autonomy**: Apply low-risk, mechanical fixes (dependency bumps, build errors, lint auto-fixes, migration-guide items) without asking. Don't pause to confirm routine steps.
- **Ask when it matters**: When a choice is ambiguous, risky, or still unresolved after the retry budget, stop and ask the user rather than guessing.
- **Target version**: Provide it in the prompt (e.g., `/angular-upgrade 21`). If it is missing, ask the user for the target major version before doing anything else.
- **On circuit breaker trip**: commit progress, generate the upgrade report with failure details, then surface the blocker to the user and **STOP**.
- 5 retries per error before circuit breaker trips.
- **Run locally, supervised**: This is a developer-run, human-in-the-loop workflow — run it from your machine, not as a hands-off CI job. Angular upgrades are too interactive to delegate end to end.
- **Micro-frontend support (Native Federation only)**: This skill supports **Native Federation** hosts/remotes as the federated stack. It does **NOT** support webpack **Module Federation** — if that is detected in Phase 0B, **STOP** (see `references/native-federation.md`). For a federated host whose remotes live in other repos, upgrading is a **lockstep** operation across host + remotes; the skill hard-stops for confirmation before proceeding.
- **Two upgrade modes — application (default) and library workspace**: an **application** repo follows the phases below (build/serve/SSR/test gates). A **publishable Angular library workspace** (ng-packagr — e.g. the repos behind `@platform/*`, `@design-system/*`, `@web-shared/*`) has no runtime render; its deliverable is bumped `peerDependencies` + rebuilt/(gated-)published libraries. Detect the mode in Phase 0B and, for a library repo, follow `references/library-upgrade.md`. For a Native Federation **fleet**, upgrade the shared-library repos **first**, then the host, then the remotes.

## Guiding Principles

- **Iterative & error-driven**: Run a command, fix the FIRST error, repeat. Do not batch fixes.
- **Small atomic changes**: One fix per iteration to isolate regressions.
- **Leverage schematics**: Always use `ng update` and official Angular schematics first.
- **Fail fast**: Circuit breakers in every phase. When tripped, commit progress, generate report, stop.
- **Never break what works**: Do not refactor working code unless the upgrade requires it.
- **Tests run once per phase gate, never per package**: exactly three suite runs — a Phase 2 baseline, one Phase 8 run, one Phase 9 confirmation. Running the suite after each package upgrade wastes time on mid-migration noise; build gates catch real breakage.
- **Record every failure**: Every test failure gets a record with file path, test name, and exact error.
- **Peer warnings ≠ errors**: Peer dependency warnings are normal mid-upgrade. Only treat install-blocking errors as stoppers.
- **Bundle shared-root-cause failures**: N specs with same root cause = 1 fix, not N.
- **Volume is never a reason to stop**: Large number of failing specs, Karma disconnect after K failures, or "pre-existing latent bug now surfaced" are NOT circuit breakers.
- **Tool priority for file operations**: Use the Read, Grep, and Glob tools (not shell `grep`/`cat`/`sed`) when reading or searching source files. Reserve bash for commands that must execute in a shell — `ng update`, `{install-command}`, `{build-command}`, `ng test`, `ng serve`, and the analysis recipes in the reference docs.

---

## Phase 0: Pre-flight Analysis & Target Version

**Goal**: Understand the project and assess upgrade risk before making any changes.

Read `references/pre-flight-checklist.md` for the full checklist.

### 0-pre. Tool Prerequisites

The recipes in this skill and its references shell out to a small fixed set of tools. Verify them up
front rather than discovering a missing one mid-phase (a missing `curl` in Phase 0D silently starves the
Phase 3B 100%-coverage audit of its source data):

```bash
missing=""
for tool in curl git node npm jq; do command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"; done
[ -n "$missing" ] && { echo "Missing required tool(s):$missing"; exit 1; }
echo "Tool prerequisites OK"
```

`jq` is needed only by `scripts/federation-discovery.sh` (federated fleets); the rest are used
throughout. All are standard in an Angular development environment — if any is absent, the environment is
misconfigured, so surface it to the user and stop rather than working around it.

### 0A. Target Version Resolution

- **FROM version**: Read from `@angular/core` in `package.json`. Never ask.
- **TO version**: Parse from the prompt (e.g., `/angular-upgrade 21`, `upgrade to Angular 21.1.0`). If the prompt contains no target version, **ask the user for the target major version** and wait for the answer before reading files or running commands.
- **Resolve exact patch**: For major-only targets, run `npm view @angular/core@{MAJOR} version`.
- **Multi-major jump**: If `{TO}` − `{FROM}` > 1 (e.g., v17 → v19), upgrade **one major at a time**. Build the ordered list `[{FROM}+1, …, {TO}]` and run the full phase cycle (Phases 1–9) for each step, resetting `{FROM}` to the just-completed major before moving to the next. Each step commits its own progress and runs its **own** Phase 3B migration-guide audit — every major has distinct migration items, so never skip the intermediate audits. If a circuit breaker trips at an intermediate major, commit, report, and stop at that version. **Every `AI/` artifact is suffixed `-v{TO}` for the step that produced it** (audit log, baseline logs, test logs) — an unsuffixed path would let each major silently overwrite the previous one's evidence, leaving the Phase 3B 100%-coverage guarantee unverifiable for every intermediate major. The Phase 9 report links the audit for each major in the chain.
- Store as `{FROM}` and `{TO}` for all subsequent phases.

### 0B. Project Discovery

1. **Detect current versions**: Angular, TypeScript, RxJS, Zone.js from `package.json`
2. **Classify project**: SSR, Express server, internal packages, PM2 configs, monorepo, **micro-frontend federation**, **library workspace** (see the detection steps below)
3. **Detect package manager**: lock file, Node version, Angular CLI version
4. **Build command map**: install, build, test, lint, lint-fix from `package.json` scripts
5. **Detect the test runner**: read `architect.test.builder` from `angular.json` plus devDependencies and store the result as `{RUNNER}`. **Never hardcode runner flags** — derive `{test-command}` and `{test-one-command}` from this table and use them in Phases 2, 8, 8B and 9:

   | `{RUNNER}` | Detection signal | `{test-command}` (full suite) | `{test-one-command}` (single spec) | Green-suite signal |
   |---|---|---|---|---|
   | `karma` | `:karma` builder, `karma.conf.js` | `ng test --watch=false --browsers=ChromeHeadless --no-code-coverage` | `{test-command} --include='<path>'` | `Executed N of M … SUCCESS` **and** no mid-run `ERROR` |
   | `vitest` | `@angular/build:unit-test` builder, `vitest` in devDependencies | `ng test --no-watch` | `ng test --no-watch -- <path>` | `Tests N passed (N)`, no `failed`, and no unhandled-error section — exact check in `test-fix-strategy.md` |
   | `jest` / other | `jest.config.*`, `@angular-builders/jest` | the repo's own `test` script from `package.json` | the runner's native filter flag | `0 failed` in the runner's own summary |

   Repos already migrated to Vitest run the `@angular/build:unit-test` builder: `--browsers` / `--no-code-coverage` are **not** valid options there, and the suite never prints `Executed`. If `{RUNNER}` is not `karma`, `references/test-fix-strategy.md`'s failure-classification table still applies but its Karma-disconnect decision tree does not.

6. **Check private registry**: `.npmrc`, `.yarnrc.yml` for private registry entries
7. **Categorize dependencies**: Into 7 groups per `references/dependency-groups-and-order.md`
8. **Create `AI/` and ensure it is gitignored**: The upgrade run writes logs, intermediate artifacts, and the final upgrade report to `AI/`. None of this should ever be committed. Run:

   ```bash
   mkdir -p AI
   grep -qxF 'AI/' .gitignore 2>/dev/null || echo 'AI/' >> .gitignore
   ```

   `mkdir -p` is required, not cosmetic: nothing else creates the directory, and every later artifact write targets it — `curl -o AI/…` in Phase 0D fails with exit 56 and `tee AI/…` with exit 1 if it is absent, which would silently starve the Phase 3B audit of its source data and push it onto the release-notes fallback. The `grep -qxF` guard appends `AI/` to `.gitignore` only if it isn't already there (idempotent); if `.gitignore` doesn't exist, the redirect creates it. Do this **before** writing anything to `AI/`.

9. **Check for a clean working tree**: Every commit step below uses `git add -A`, which would sweep in any pre-existing uncommitted changes. Run `git status --porcelain`; if the tree is dirty, list the changes and **ask the user** whether to proceed (recommend they stash or commit unrelated work first). On a fresh CI/worktree checkout this is a no-op.
10. **Check the current branch**: This skill makes 7+ commits across phases. Run `git rev-parse --abbrev-ref HEAD`. If the branch is `main`, `master`, or your team's integration branch, **ask the user** before proceeding — offer to create a feature branch first (`git checkout -b feat/angular-upgrade-v{TO}`) so the commits stay reviewable. If already on a feature branch, proceed without pausing.
11. **Record the rollback point**: this skill makes 7+ `git add -A` commits and rewrites `package.json` + the lock file, and any phase can hard-stop. Capture a known-good state first:

    ```bash
    git rev-parse HEAD > AI/upgrade-start-sha
    git tag "pre-angular-upgrade-v{TO}"      # local only, never pushed
    ```

    Every circuit-breaker stop, the final report, and any Phase 10 promotion block must state: **"To abandon: `git reset --hard pre-angular-upgrade-v{TO} && {install-command}`."**

### Micro-frontend Federation Detection (Native Federation only)

Detect the federation stack per `references/native-federation.md` before proceeding:

- **Module Federation detected** (any `*module-federation*` package — `@angular-architects/module-federation*` **or the internal `@your-org/module-federation`**; `webpack.config.js` with `ModuleFederationPlugin`/`withModuleFederationPlugin`; `ngx-build-plus` / `@angular-builders/custom-webpack` builder) → **STOP**. This skill supports Native Federation only. Surface the Native-Federation migration path from `references/native-federation.md` and do not proceed. If **both** NF and MF signals are present (mid-migration / stale deps), ask the user which is authoritative rather than proceeding.
- **Native Federation detected** (`@angular-architects/native-federation[-v4]`, `federation.config.{js,mjs}`, an `@angular-architects/native-federation:*` builder, `federation.manifest.json`; on **Nx**, the same in `project.json`) → record the **role** (host / remote / host+remote), the **current line** (v3 = `.js`/`@softarc/*@3.x`, v4 = `.mjs`/`@softarc/*@4.x`), and the remote inventory in the discovery summary.
- **Native Federation host consuming remotes in OTHER repos** → **STOP and require lockstep confirmation** before proceeding, **and require a cross-repo singleton-reconciliation manifest to exist first** — one agreed pinned version for every `singleton: true` shared dep across host + all remotes (Angular framework pinned to the *exact* target patch). Each per-repo run then pins its singletons to that manifest, and Phase 8B is forbidden from bumping a singleton past it. Host and remotes negotiate shared singletons by **version** at runtime; independent per-repo resolution drifts them apart and a green build won't catch it. Same-repo/monorepo remotes are upgraded together. See "Cross-repo singleton reconciliation" in `references/native-federation.md` — `scripts/federation-discovery.sh` generates the manifest skeleton (inventory + drift) from a GitLab namespace, read-only, no cloning.

### Library Workspace Detection

Some repos are **publishable Angular library workspaces** (ng-packagr), not apps — e.g. the shared-library repos behind `@platform/*`, `@design-system/*`, `@web-shared/*`. Signals: `angular.json` `projects.*` of type `library`, `ng-packagr` in devDependencies, `projects/<lib>/ng-package.json`, per-library `projects/<lib>/package.json` carrying `peerDependencies`, and root `private: true` + a publish script (no `federation.config.*` / app bootstrap).

If detected, this is a **library upgrade**, not an application upgrade — follow `references/library-upgrade.md` (build via the repo's own script, no `ng serve`/SSR/runtime render; the core deliverable is bumping each library's `peerDependencies` to the target; publishing is a gated release step). For a **Native Federation fleet, upgrade the shared-library repos first** (they publish the target-major singletons the host + remotes consume), then the apps.

### Monorepo Handling

If multiple Angular projects are detected (more than one entry under `projects` in `angular.json`, or multiple `package.json` files containing `@angular/core`), this skill upgrades **one project at a time**. A root-level `ng update` can update shared packages and break sibling projects that have not been upgraded.

- Ask the user which project to target (or honour a `--project=<name>` hint in the prompt).
- Once a single project is chosen, scope every command and path reference ({install-command}, {build-command}, {test-command}, `angular.json`, etc.) to that project's root — not the workspace root.

### 0C. tsconfig Inspection (Angular 19+)

Read `references/tsconfig-migration.md`. If `moduleResolution` is `"node"`, fix to `"bundler"` **before** starting the upgrade loop.

### 0D. Fetch Official Angular Update Guide (MANDATORY)

Fetch the raw recommendations data from the Angular GitHub repository (`-f` makes curl fail on a 404 instead of saving the error page as if it were the guide):

```bash
curl -fsSL "https://raw.githubusercontent.com/angular/angular/{TO}.0.x/adev/src/app/features/update/recommendations.ts" -o AI/angular-update-guide-v{TO}.ts
```

Fallback URL (if branch doesn't exist):
```bash
curl -fsSL "https://raw.githubusercontent.com/angular/angular/{TO}.0.0/adev/src/app/features/update/recommendations.ts" -o AI/angular-update-guide-v{TO}.ts
```

Verify the file was fetched and contains data for the target version. Count migration **objects** at the target — an item may carry `possibleIn`, `necessaryAsOf`, or (commonly) **both** equal to `{TO}00`, so count objects, not matching lines. A raw line grep roughly **doubles** the total by counting both fields of the same item:
```bash
# Count migration OBJECTS at the target: items carry BOTH possibleIn and necessaryAsOf, so a LINE
# count roughly doubles them. Walk top-level {...} objects by brace depth and count the tagged ones.
# Do NOT substitute a non-nested regex like {[^{}]*} — it silently drops every item that nests an
# object (measured on the real v21 file: 18 vs the correct 20), which breaks the 100%-coverage
# mandate in Phase 3B. Node is used rather than perl/awk because an Angular repo always has it.
node -e '
const fs = require("fs");
const [file, major] = process.argv.slice(1);
const src = fs.readFileSync(file, "utf8");
const tagged = new RegExp("(possibleIn|necessaryAsOf):\\s*" + major + "00");
let count = 0, depth = 0, start = -1;
for (let i = 0; i < src.length; i++) {
  const ch = src[i];
  if (ch === "{") { if (depth === 0) start = i; depth++; }
  else if (ch === "}" && depth > 0) {
    depth--;
    if (depth === 0 && start >= 0) { if (tagged.test(src.slice(start, i + 1))) count++; start = -1; }
  }
}
console.log(count);
' AI/angular-update-guide-v{TO}.ts {TO} | tee AI/migration-total-v{TO}.txt
```

This is the **single** canonical item count — Phase 3B reads `AI/migration-total-v{TO}.txt` as `{TOTAL}` rather than recomputing it, so the denominator of the 100%-coverage check can never drift from the number reported here.

If the count is **0 or the file is empty/missing**, fall back to release notes:
1. WebFetch `https://github.com/angular/angular/releases/tag/{TO}.0.0`
2. WebFetch `https://blog.angular.dev/` (find the v{TO} release announcement)
3. Extract all breaking changes, deprecations, and migration steps into `AI/angular-update-guide-v{TO}.md`
4. Use this as the Phase 3B audit source instead

This is the structured data source behind `angular.dev/update-guide`. Each entry has:
- `possibleIn` / `necessaryAsOf` — version code (e.g., `2100` = v21)
- `step` — identifier
- `action` — what to do
- `level` — Basic / Medium / Advanced
- Optional flags: `material`, `angularCLI`, `ngUpgrade`

**Every item must be audited in Phase 3B. No exceptions.**

### 0E. Risk Assessment & Discovery Summary

Log risk assessment and discovery summary (template in `references/pre-flight-checklist.md`). **Proceed immediately** — do NOT pause for confirmation.

---

## Phase 1: Upgrade Plan

**Goal**: Show the full upgrade plan, then proceed.

For each in-scope package, look up the correct target version (check npm registry or Angular compatibility matrix).

```
Upgrade Plan
────────────
Current Angular: v{FROM}
Target Angular:  v{TO}

Packages to upgrade ({count}):
  Group 1 — Angular Core
    @angular/core              {current} → {target}
    ... (all Group 1)
  Group 2-5 ... (all groups with packages)

Packages staying as-is ({count}):
  {package}  {version}  (reason)

Node.js compatibility:
  Angular v{TO} requires Node.js v{min}.
  Current: v{current}   ← OK / WARNING
```

Log the plan and proceed immediately.

---

## Phase 2: Baseline Build Check

**Goal**: Confirm the project builds before making changes.

```bash
{install-command}
{build-command}
```

Record: Build PASS / FAIL. Capture the full build, lint and test output to per-major baseline logs so pre-existing failures can be told apart later. All three are consumed downstream — this is not diagnostic noise:

```bash
{build-command} 2>&1 | tee AI/baseline-build-v{TO}.log
{lint-command}  2>&1 | tee AI/baseline-lint-v{TO}.log  | tail -10
{test-command}  2>&1 | tee AI/baseline-test-v{TO}.log  | tail -20
```

`{test-command}` comes from the Phase 0B step 5 runner table — never a hardcoded `ng test …` invocation.

**How each baseline is used** (a captured baseline that nothing reads is worse than none — it implies an attribution guarantee the skill would not actually honour):

| Baseline | Consumed by | Behaviour |
|---|---|---|
| `AI/baseline-build-v{TO}.log` | Phase 3 Step B + Phase 5 | Extract error signatures (error code + module/symbol) and **skip-and-mark** any matching error instead of spending the 20-iteration budget on a failure the upgrade did not cause. |
| `AI/baseline-lint-v{TO}.log` | Phase 6 | Violations present in the baseline are **pre-existing** — excluded from the 3-round circuit breaker and reported, not fixed, unless the user asks. |
| `AI/baseline-test-v{TO}.log` | Phase 8 | Specs failing in the baseline are **pre-existing** — excluded from the 5-attempt budget and the circuit breaker (see Phase 8 → "Diff against the baseline first"). |

If the build is already broken:
- Surface the broken baseline to the user and ask whether to proceed — a project that doesn't build *before* the upgrade can't produce a trustworthy "upgrade-caused failure" signal.
- Do not conflate pre-existing failures with upgrade-caused failures in the report.

---

## Phase 3: Dependency Upgrade

**Goal**: Update all Angular and related packages to the target version.

Read `references/dependency-groups-and-order.md` for the strict upgrade order.
Read `references/internal-packages.md` for handling @your-org/*, @web-shared/*, @design-system/*, @platform/* packages.
Read `references/third-party-compat.md` for known third-party package issues.

### Upgrade Process

Work through packages in group order (1 → 7). For each package:

**Step A — Upgrade the package**

Try `ng update` first (it runs Angular schematics):
```bash
npx ng update {package}@{target-version} --allow-dirty --force
```

If unavailable or fails, fall back to direct bump:
```bash
{pkg-manager} add {package}@{target-version}     # dependency
{pkg-manager} add -D {package}@{target-version}   # devDependency
```

Then: `{install-command}`

> **Realign `pnpm.overrides` / `resolutions`:** `ng update` bumps top-level deps but does **not** touch a `pnpm.overrides` (or npm/yarn `resolutions`) block. If `package.json` pins any `@angular/*` or other `singleton` dep there — e.g. `@angular/cdk` / `@angular/material` / `@angular/animations` held at the old major — the app silently resolves a **mixed** Angular version set. After `ng update`, scan `overrides`/`resolutions` for pinned `@angular/*` / singleton versions and realign them to the target.

**Peer dependency handling:**

| Situation | Action |
|-----------|--------|
| Another package in same group blocks | Reorder — upgrade blocking package first |
| Third-party requires old version | Find compatible newer version; skip if none |
| Strict peer deps blocking (pnpm) | Add `strict-peer-dependencies=false` to `.npmrc` |
| Internal package conflict | Re-run with `--force` |

**Step B — Build validation gate**

```bash
{build-command}
```

If build fails, auto-fix without asking:

Read `references/build-fix-patterns.md` for error→fix table. Fix the FIRST error, re-run build, repeat until PASS.

- **DO fix**: anything causing a compile error
- **DO NOT touch**: code that still compiles, even if newer style exists

**Step C — Lint gate (quick)**

```bash
{lint-fix-command}
{lint-command}
```

Auto-fix lint errors introduced by the upgrade. See `references/lint-fix-strategy.md`.

> **Pre-commit `lint-staged` blocker:** If `lint-staged` runs on staged files and finds pre-existing violations in files you touched, fix the offending lines following `references/lint-fix-strategy.md`. **Never add `// eslint-disable` comments** and never bypass the hook with `--no-verify` — this matches the Phase 6 hard rules and `lint-fix-strategy.md`. If a violation genuinely can't be fixed without an out-of-scope refactor, record it in the upgrade report and surface it to the user.

**Step D — Log progress**

```
✅ {package-name}  {old-version} → {new-version}
   Method:  ng update (schematics) | manual bump
   Build:   PASS
   Lint:    PASS  [N auto-fixed]
```

If a package cannot be upgraded:
```
⏭️  SKIPPED: {package}
    Reason: {no compatible version / private registry / unresolvable}
    Action: Pinned at {current-version}
```

### Native Federation Adapter (if applicable)

If the project uses Native Federation, upgrade the adapter **right after Angular core + CLI** — it rides Angular's `ApplicationBuilder` and must match the just-installed Angular. The adapter is **version-locked to the Angular major** (like CDK/Material), not a "latest that works" bump, and installing the wrong package for the line is itself a break.

Which package, whether a config migration applies, and the v3-vs-v4 decision on Angular 20/21 (including when to **ask the user**) are defined **once** in `references/native-federation.md` → "Adapter package selection"; the operational step sits at Step 2b of `references/dependency-groups-and-order.md`. Follow those — do not re-derive the version rules here.

### Commit After All Dependencies

After ALL packages in all groups are upgraded:
```bash
git add -A
git commit -m "feat: upgrade Angular dependencies to v{TARGET}"
```

### Circuit Breakers

- **Same error 5 times**: Commit progress, generate report with stuck error details, **STOP**.
- **20 total build-fix iterations**: Commit progress, generate report with remaining errors, **STOP**.
- **Unknown error**: If not in knowledge base or update guide, commit, report, **STOP**.

> **Definition of "same error"** (applies to every "same error N times" breaker in this skill): two errors are the *same* when they share the same error code (e.g., `TS2307`, `TS2345`, `NG0xxx`) **and** the same root cause (same missing module, same incompatible type shape). Differing file paths or line numbers do **not** make them distinct — track by code + root cause, not by the full message string.

---

## Phase 3B: Migration Guide Audit (MANDATORY — NO ITEMS MAY BE SKIPPED)

**Goal**: Audit every item from the official Angular update guide against the codebase and apply all applicable changes.

Uses `AI/angular-update-guide-v{TO}.ts` fetched in Phase 0D.

### Process

**Step 1 — Extract all migration items**

Extract every entry whose `possibleIn` **or** `necessaryAsOf` is `{TO}00` (e.g., `2100` for v21). Items encoded as `possibleIn: 1900, necessaryAsOf: 2100` *become required* at the target even though they were possible earlier — counting only `possibleIn` silently drops them and breaks the 100% coverage guarantee below.

```bash
TOTAL=$(cat AI/migration-total-v{TO}.txt)      # the canonical count from Phase 0D — do NOT recompute
echo "Total migration items to audit: $TOTAL"
```

Reusing the Phase 0D number is deliberate: two copies of a brace-depth scanner can drift, and a
denominator that drifts downward would let this phase report 100% coverage while never having seen an item.
If the file is missing, re-run the Phase 0D counter — do not substitute a line grep or a non-nested regex.

In the audit log, tag each row with which field matched (`possible@{TO}` vs `necessary@{TO}`) so a reviewer can tell "newly possible" from "now required."

**Step 2 — Audit each item against the codebase**

For **every** extracted item, search the codebase to determine applicability:

| Status | Meaning |
|--------|---------|
| ✅ ALREADY HANDLED | The required change is already present in the codebase |
| 🔧 APPLICABLE — FIXED | The item applied to this codebase and has been fixed |
| ⬜ NOT APPLICABLE | The codebase does not use the affected API/feature |
| ❌ APPLICABLE — NEEDS MANUAL ACTION | Cannot be auto-fixed, documented for the developer |

For each item:
1. Read the `step` identifier and `action` description
2. Search the codebase for the affected API, pattern, or configuration
3. If applicable, apply the fix
4. If not applicable, document why (e.g., "project does not use `@angular/elements`")

**Step 3 — Generate the audit log**

Create **`AI/migration-guide-audit-v{TO}.md`** using the "Migration Guide Audit" template in `references/upgrade-report-template.md`. The `-v{TO}` suffix is mandatory: on a multi-major run each step audits a different item set, and an unsuffixed path would overwrite the previous major's evidence.

### Native Federation migration items (if applicable)

The Angular update guide does **not** cover Native Federation. If the project is federated, additionally audit the native-federation migration items — `federation.config.js`→`.mjs`/ESM, `@softarc/*` v4 bumps and `shareAll()` overrides, `fstart.mjs` / `bootstrap.server.ts` server changes, and the SSR-keeps-Classic-Runtime rule — from `references/native-federation.md`, and fold them into `AI/migration-guide-audit-v{TO}.md` under the same 100%-coverage discipline (add them as extra rows tagged `native-federation`).

### Guardrails — These are NON-NEGOTIABLE

1. **100% audit coverage**: The `Audited` count MUST equal `Total`. `Total` is the **object** count produced by the Phase 0D brace-depth scanner and read from `AI/migration-total-v{TO}.txt` — never a raw line grep, which double-counts every item carrying both `possibleIn` and `necessaryAsOf` (both-fields-at-target is the norm: on the real files, 26 items show as 52 lines at v20, 20 as 40 at v21, 37 as 74 at v22). If any item is not audited, this phase has FAILED. Do NOT proceed to Phase 4.

2. **No silent skips**: Every item must have an explicit status and notes explaining why it is or isn't applicable. "Skipped" is NOT a valid status.

3. **Verify after applying**: After fixing all applicable items, run:
   ```bash
   {build-command}
   ```
   If the build breaks, fix before proceeding.

4. **Runtime verification**: After all items are addressed, serve the app locally and verify the main page *actually renders* — HTTP 200 **and** an `ng-version` marker (not a 200 error page). Run the **CSR runtime check** in `references/runtime-verification.md`; if it fails, investigate and surface to the user before proceeding. For federated apps that reference also covers the Native Federation caveats (remote → assert `remoteEntry.json`; host → shell-200 is necessary-but-not-sufficient).

5. **Completion gate**: This phase is complete ONLY when:
   - All {TOTAL} items are audited (no exceptions)
   - All applicable items are fixed or documented as needing manual action
   - Build passes
   - Runtime check passes (HTTP 200)

### Commit

```bash
git add -A
git commit -m "fix: apply Angular v{TO} migration guide changes"
```

---

## Phase 4: SSR Migration (if applicable)

**Goal**: Update SSR configuration for the new Angular version.

Skip only if **none** of these SSR signals is present — a single-signal `ssr`-key check under-detects legacy Angular Universal (a separate `server` architect target with no `ssr` key), which would silently skip this entire phase *and* its boot check on an SSR repo and let `@angular/ssr/node` API drift ship behind a green build:

- an `ssr` key or `"outputMode": "server"` under the build target in `angular.json`
- a `server` or `ssr` architect target (legacy Angular Universal layout)
- `@angular/ssr` or `@nguniversal/*` in `dependencies`
- a `src/server.ts` or `src/main.server.ts` file

If the repo is on legacy `@nguniversal/*`, migrating it to `@angular/ssr` is itself a target-version migration item — audit it in Phase 3B rather than treating it as out of scope.

Read `references/ssr-migration-patterns.md` for detailed patterns.

### What to Review, and What to Leave Alone

`references/ssr-migration-patterns.md` is canonical for both — it lists the five critical files
(`src/server.ts`, `app.config.server.ts`, `app.routes.server.ts`, `main.server.ts`, `angular.json`) with
their current patterns, the target-version API surface to check (`AngularNodeAppEngine`,
`createNodeRequestHandler`, `writeResponseToNodeResponse`, `provideServerRendering(withRoutes(...))`,
`outputMode: "server"`, Express 5 `/{*path}`), and the **do-not-touch** set (CSP middleware and nonce
injection, business redirects, Prometheus/Morgan/heap-dump endpoints, XSS sanitisation, UA parsing).

Those exclusions are business-specific and Angular-independent: touch them only if the *helmet* or
*Express* API itself changed, never because the upgrade offered a newer idiom.

For **Native Federation** SSR also read `references/native-federation.md` (federation initialises
server-side; adapter v20+ emits `dist/{project}/server/fstart.mjs`, which is what PM2 must start; the SSR
path stays on the Classic Runtime — the Orchestrator is client-only).

### Verify the SSR Server Boots (not just the build)

A passing production build does **not** prove SSR works — the server can still crash on boot or throw at request time (`@angular/ssr/node` API drift, `XhrFactory`/`xhr2`, externalized native deps). After the SSR build succeeds, run the **SSR boot check** in `references/runtime-verification.md`: it starts the SSR dev server (preferring `fstart.mjs` for Native Federation v20+) and asserts HTTP 200 + `ng-version` + a clean server log. Record the result (and the SSR dev-server start time — see Phase 9) in the upgrade report; if it fails, surface it before proceeding.

### Commit

```bash
git add -A
git commit -m "fix: update SSR configuration for Angular v{TARGET}"
```

---

## Phase 5: Build-Fix Loop

**Goal**: Get the production build passing after all upgrades.

1. Run: `{build-command}`
2. If build succeeds → Phase 6
3. If build fails:
   a. Read the FIRST error
   b. Check `references/build-fix-patterns.md` and version-specific knowledge base
   c. Apply smallest possible fix
   d. Go to step 1

### Circuit Breakers

- **Same error 5 times**: Commit progress, generate report, **STOP**.
- **20 total iterations**: Commit progress, generate report, **STOP**.

### Commit

```bash
git add -A
git commit -m "fix: resolve build errors post-upgrade to Angular v{TARGET}"
```

---

## Phase 6: Lint Fix

**Goal**: Fix all ESLint errors introduced by the upgrade.

Read `references/lint-fix-strategy.md` for the anti-loop strategy.

### Hard Rules

- **NEVER modify `.eslintrc`, `eslint.config.mjs`, or `@your-org/eslint-config` rules**
- **NEVER add `// eslint-disable` comments** to suppress errors
- **NEVER convert existing non-standalone components to standalone** unless the upgrade explicitly requires it

### Process

1. Run: `{lint-fix-command}` (auto-fixes what it can)
2. Run: `{lint-command}` to see remaining errors
3. Group remaining errors by ESLint rule code
4. Fix one rule category at a time, starting with most frequent
5. After fixing a category, re-run lint to verify
6. Repeat for next category

### Pre-existing violations

Diff the remaining violations against `AI/baseline-lint-v{TO}.log` (Phase 2). Any violation present in the baseline is **pre-existing**, not upgrade-caused: exclude it from the circuit-breaker rounds below, report it under "Pre-existing, not upgrade-caused", and fix it only if the user asks. The `lint-staged` exception in Phase 3 Step C still stands — a pre-existing violation on a line you *touched* must be fixed to get past the pre-commit hook.

### Circuit Breaker

- **3 full rounds** of lint → fix → lint with no progress on *upgrade-caused* violations: Commit progress, generate report with remaining lint errors, **STOP**.

### Commit

```bash
git add -A
git commit -m "fix: resolve lint errors post-upgrade to Angular v{TARGET}"
```

---

## Phase 7: Deprecation Sweep

**Goal**: Replace deprecated Angular APIs with their modern replacements.

Read `references/deprecation-sweep.md` for the deprecated→replacement table.

### Rule

**Deprecated = update it. Supported but old-style = leave it alone.**

1. Search `src/` for each deprecated pattern relevant to this migration's version range
2. Confirm each hit is genuinely deprecated in the target version
3. Apply the replacement
4. Run build to confirm nothing broke

### Commit

```bash
git add -A
git commit -m "chore: replace deprecated Angular APIs after v{FROM}→v{TO} upgrade"
```

---

## Phase 8: Test Fix

**Goal**: Get all tests passing.

Read `references/test-fix-strategy.md` for detailed patterns and — on Karma only — the mid-run error decision tree.

Every command in this phase uses `{test-command}` / `{test-one-command}` from the Phase 0B step 5 runner table. **Do not hardcode Karma flags**: `--browsers` and `--no-code-coverage` are invalid on `@angular/build:unit-test`, so a hardcoded invocation fails outright on a Vitest-migrated repo.

### Pre-test: Run Full Suite ONCE

```bash
{test-command} 2>&1 | tee AI/test-run-v{TO}.log
```

On `{RUNNER}` = `karma`, if the run ends with `ERROR`, apply the mid-run Chrome ERROR decision tree from `references/test-fix-strategy.md` before treating the log as complete. On `vitest`, the equivalent signal is a non-zero `Unhandled Errors` count — treat it the same way (the log is incomplete, not green).

### Extract Failing Specs

From the log, extract failing suite names and map to spec file paths. See `references/test-fix-strategy.md` for the extraction recipe (per runner).

### Diff against the baseline first

Extract the failing spec set from `AI/baseline-test-v{TO}.log` (Phase 2). Any failure present in **both** sets is **pre-existing**, not upgrade-caused: mark it `PRE-EXISTING` in `AI/angular-upgrade-test-failures-v{TO}.md`, exclude it from the 5-attempt budget and from the circuit breaker, and list it in the report under "Pre-existing, not upgrade-caused". Fix it only if the user asks. Without this diff, an already-red spec can trip the circuit breaker on a failure the upgrade never caused — which would contradict Phase 2's attribution rule.

### Fix Iteratively

For each *upgrade-caused* failing spec:
```bash
{test-one-command}    # karma: {test-command} --include='**/path/to/failing.component.spec.ts'
                      # vitest: ng test --no-watch -- path/to/failing.component.spec.ts
```

Fix → re-run that spec → move to next. **Do NOT re-run the full suite after each fix.**

### Record Failures

Create `AI/angular-upgrade-test-failures-v{TO}.md` with file path, test name, exact error, and status (`PRE-EXISTING` where the baseline diff said so) for each failure. See format in `references/test-fix-strategy.md`. (Under `AI/` so it stays gitignored and out of the upgrade commits.)

### Classify Each Failure

Classify every failure as **Infrastructure** (auto-fix, re-run the spec), **Actual regression** (record, report, **STOP** after 5 attempts), or **Flaky** (mark, don't block). See `references/test-fix-strategy.md` for the full classification table with definitions.

### What is NOT a Reason to Bail

The following are **not** circuit breakers:

- **"Large number of failing specs"** — volume alone is never a reason to stop. N specs failing with same root cause = **one fix**. Find the shared fix: global test provider, shared mock factory, component/template fix.
- **"Too many specs to fix in one go"** — volume is not a stop condition. The skill is built to grind through large batches; keep fixing as long as each fix makes progress.
- **"Runner disconnect after K failures"** — Karma disconnect, or a Vitest worker crash, means switch to per-file mode (`{test-one-command}`) and keep fixing.
- **"Pre-existing latent bug now surfaced"** — an upgrade-caused failure whose *root cause* predates the upgrade is still in scope: surface ≠ out-of-scope. This is distinct from a spec that was **already red in `AI/baseline-test-v{TO}.log`** — that one is excluded per "Diff against the baseline first" above.

Before stopping, you must point to a **specific test whose failure you cannot resolve after 5 distinct fix attempts**.

### Bundling Shared-Root-Cause Failures

When the same failure signature appears across many specs:
1. Fix once in the most appropriate place (component, shared helper, global provider)
2. Re-run 2-3 representative specs to confirm the single fix clears the class
3. Move to next distinct failure signature
4. Do not open N files to apply the same fix N times

### Hard Rules

- **NEVER use `xit()` or `xdescribe()`** to skip tests
- **NEVER delete test cases**
- **NEVER reduce code coverage**

### Circuit Breaker (real)

- **Same individual test failing 5 times with 5 distinct fix approaches**: This is the only trigger for stopping.

### Commit

```bash
git add -A
git commit -m "fix: resolve test failures post-upgrade to Angular v{TARGET}"
```

---

## Phase 8B: Third-Party Dependency Review & Upgrade

**Goal**: Now that Angular itself is upgraded, build-green, and tests pass, bring **applicable** third-party (Group 5) packages up to date and report the rest. Runs only after Phases 5–8 are green — never let third-party churn block the core Angular upgrade.

Read `references/third-party-compat.md` for the detection, compatibility-check, and reporting procedure (and the curated gotcha list).

### Process

Goal: by the end of this phase, **every** third-party (Group 5) Angular-ecosystem package sits at the highest version compatible with Angular v{TO} — not just the ones that broke the build in Phase 3.

The five-step procedure (enumerate → resolve target version → upgrade one at a time behind the build gate → defer only when forced → report) lives in `references/third-party-compat.md` → "Post-Angular Review & Upgrade (Phase 8B)". Follow it there; the guardrails below are what this phase adds on top.

### Guardrails

- **Attempt every package** — this phase is not report-only. The report records what was upgraded and what was deferred, after actually trying each one.
- Keep scope to the Angular ecosystem. Do **not** fold unrelated/non-Angular dependency bumps into the Angular upgrade — that is a separate task.
- A package upgrade that breaks the build/tests and can't be resolved within the retry budget is **reverted and deferred**, not left half-applied.
- **Major bumps read the changelog first.** For any package crossing a major version, consult its release notes / CHANGELOG / migration guide and apply the documented migrations *before* leaning on the build+test gate — that gate misses runtime/behavioral breaking changes, silent deprecations, and renamed config/inputs. Minor/patch bumps trust semver (build+test suffices). See `references/third-party-compat.md`.
- **Federated apps — freeze singletons.** Do **not** bump a shared `singleton: true` dependency past the reconciled cross-repo pin (see "Cross-repo singleton reconciliation" in `references/native-federation.md`). Singletons stay frozen to the agreed manifest so host + remotes hold identical versions; only non-singleton libs are swept here.

### Commit

```bash
git add -A
git commit -m "chore: upgrade compatible third-party dependencies after Angular v{TO} upgrade"
```

---

## Phase 9: Final Validation & Report

**Goal**: Final verification and upgrade documentation.

Read `references/upgrade-report-template.md` for the report format.
Read `references/pm2-and-deployment.md` for PM2 config checks (if applicable).

### Final Verification

1. Run full production build: `{prod-build-command}`
2. Run full test suite: `{test-command} 2>&1 | tee AI/test-final-v{TO}.log`
3. Both must pass. If either fails, loop back to Phase 5 or 8 respectively.
4. The suite is "passing" only if there are **zero failures AND no mid-run error** — which looks different per runner, so assert it with the matching **runner-aware green-suite check in `references/test-fix-strategy.md`** ("Asserting a green suite") rather than eyeballing the log. Run it under `bash`. A mid-run error is a Phase 8 regression — fix the underlying bug, don't re-run hoping for green.

   > **Never assert Karma's grammar against a non-Karma runner.** Karma prints `Executed N of M … SUCCESS`; Vitest prints `Tests N passed (N)` and never prints `Executed`. Grepping for the Karma line on a Vitest repo makes a fully green suite read as a failure, and step 3 would then loop back to Phase 8 forever on a correct upgrade.

5. Check PM2 configs: verify `dist/server/server.mjs` entry point is valid after build.
6. If SSR: re-confirm the SSR server boots and renders (Phase 4 → "Verify the SSR Server Boots"). A green production build is not sufficient evidence on its own.

### Capture Performance Metrics

Record these in the report so regressions are visible (e.g., native-federation builds can be *slower*, not faster, than webpack):

```bash
# Production build time
/usr/bin/time -p {prod-build-command} 2>&1 | tee AI/build-timing.log
```

Capture at minimum: **production build time** and, for SSR projects, **SSR dev-server start time** (seconds from launch to first HTTP 200 — reuse the boot-check loop from Phase 4). Note the build system (webpack vs esbuild / native-federation) next to the numbers.

### Generate Deployment Checklist

Produce `AI/deployment-checklist.md` from `references/deployment-checklist.md`. Most important: if Angular v{TO} requires a newer **Node.js** than the current server/CI images use, call it out explicitly so SRE can update the images before deploy.

### Generate Upgrade Report

Create `AI/upgrade-report-v{FROM}-to-v{TO}.md` using the template in `references/upgrade-report-template.md`. The **top of the report must carry an overall status banner** (PASS / FAIL / PENDING / BLOCKED) with any blockers and action items.

### Final Commit

```bash
git add -A
git commit -m "chore: Angular v{FROM}→v{TO} upgrade report and final cleanup"
```

### Push & Open MR

The upgrade produces 7+ commits — push the branch and open a **GitLab MR** so they're reviewable rather than sitting locally. Internal web repos are on **GitLab** — use `glab`, not `gh`/PR conventions:

```bash
git push -u origin HEAD
# glab has NO --description-file — pass --description inline (flags differ from gh).
glab mr create --source-branch "$(git rev-parse --abbrev-ref HEAD)" --target-branch {integration-branch} \
  --title "chore: Angular v{FROM}→v{TO} upgrade" \
  --description "$(sed -n '1,40p' AI/upgrade-report-v{FROM}-to-v{TO}.md)" --draft
```

Target your team's integration branch (confirm it). The description should carry the overall status banner (PASS / FAIL / PENDING / BLOCKED) from the upgrade report plus any blockers or deferred items. Confirm with the user before pushing if the branch or target isn't obvious.

---

## Phase 10: Post-Deploy Verification (federated apps — after each environment deploy)

**Goal**: Verify the artifact a **browser** loads, not just the one the build produced.

Read `references/post-deploy-verification.md`.

> **This phase runs in a separate, later session.** Phases 0–9 end with the MR pushed; the deploy happens
> after it merges, so Phase 10 cannot execute in the same run. **Re-enter** by invoking this skill with the
> environment — `/angular-upgrade verify-deploy stage` — or by saying "verify the deploy", "remotes broken
> after deploy", "singleton skew"; then skip Phases 0–9 and start here. Phase 0-pre (tool prerequisites)
> and Phase 0B's federation detection still apply, nothing else does.
>
> **Where results go:** if the upgrade branch is still open, add the **Post-Deploy Verification** section
> (template in `references/upgrade-report-template.md`) to `AI/upgrade-report-v{FROM}-to-v{TO}.md` and
> amend it into the report commit. If the branch is already merged, do **not** reopen it — record the
> results in `AI/deployment-checklist.md` and post them on the merged MR thread, so the promotion decision
> is auditable where the reviewer will look for it.

Phases 0–9 all run against source and local build output, so they cannot observe failures that
*deployment* produces. Three classes have reached production through fully green Phase 9 gates: stale
host `remoteEntry.json` in warm browsers (lazy routes throw `does not provide an export named 'X'`),
singleton version drift resolved silently at runtime by highest-wins, and a blue/green promotion copying
the staging CDN config over primary. A green report is therefore **not** the end of the upgrade for a
federated fleet.

Run after deploying to each environment and **before promoting** it. All five procedures — the exact
commands, thresholds and failure signatures — are in `references/post-deploy-verification.md`:

1. **Resolve the true shared set** — *evaluate* `federation.config.*` with node rather than parsing it; a
   config that spreads an imported share map hides most package names from any static parse (which is why
   `scripts/federation-discovery.sh` marks those rows `share(N)!`). Confirm it matches the reconciliation
   manifest.
2. **Live singleton skew sweep** — every shared entry, not a framework shortlist; observed skews were
   third-party `ngx-*` packages. **Any output is a promotion blocker.**
3. **Cache headers** — host `remoteEntry.json`, the manifest and `index.html` must all be
   `no-cache`/`no-store`; a long `max-age` *and* an absent header both poison warm browsers, and fixing the
   header does not repair browsers already holding a copy (only a URL change does — see the `cacheTag`
   pattern).
4. **Warm-browser check** — in a profile that visited the previous deploy, never incognito; incognito
   cannot reproduce this class.
5. **Blue/green promotion diff** — only origins and genuinely new routes may differ; cache policies,
   response-header policies, TTLs and viewer-protocol policy must match primary.

Record the results in the upgrade report's **Post-Deploy Verification** section. `strictVersion: false`
singletons need *more* scrutiny than strict ones: strict mismatches throw and are self-announcing,
non-strict mismatches are silently substituted and pass a smoke test.
