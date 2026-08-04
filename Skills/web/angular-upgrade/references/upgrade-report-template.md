# Upgrade Report Template

Generate this report as `AI/upgrade-report-v{FROM}-to-v{TO}.md` after the upgrade.

Two sections double as standalone artifacts:

- **Migration Guide Audit (Phase 3B)** — Phase 3B writes the same structure to its own file per major,
  `AI/migration-guide-audit-v{TO}.md`, tagging each row's `Trigger` as `possible@{TO}` or
  `necessary@{TO}` so a reviewer can tell "newly possible" from "now required". On a multi-major run
  there is one such file per step and this report links them all.
- **Post-Deploy Verification (Phase 10)** — filled in a later session, after deploy. Keep it as
  `NOT RUN` until then rather than deleting it.

Everything inside the fenced block below is report content — copy it out and fill it in. (The `## `
lines in it are template sections, not sections of *this* file, so this document has no table of
contents.)

---

```markdown
# Angular v{FROM} → v{TO} Upgrade Report

**Date**: {YYYY-MM-DD}
**Project**: {project name from package.json}
**AI Model**: {model name}

## Status

> **Overall: {PASS | FAIL | PENDING | BLOCKED}**

| Gate | Result |
|------|--------|
| Production build | PASS / FAIL |
| SSR server boot (if SSR) | PASS / FAIL / N/A |
| Test suite | PASS / FAIL |
| Lint | PASS / FAIL |
| Migration guide audit | {AUDITED}/{TOTAL} |

**Blockers / action items**: {bullet list, or "none"}

## Upgrade Summary

| Item | Before | After |
|------|--------|-------|
| @angular/core | {old} | {new} |
| @angular/cli | {old} | {new} |
| @angular/material | {old} | {new} |
| @angular/cdk | {old} | {new} |
| @angular/ssr | {old} | {new} |
| TypeScript | {old} | {new} |
| RxJS | {old} | {new} |
| Zone.js | {old} | {new} |

### Packages Upgraded by Group

  Group 1 — Angular Core
    @angular/core              {old} → {new}
    ... (full list)

  Group 2-5 ... (all upgraded groups)

### Packages Skipped

| Package | Version | Reason |
|---------|---------|--------|
| {name} | {version} | {reason: no compatible version / out of scope / internal} |

## Migration Guide Audit (Phase 3B)

- **Source**: `angular/angular/{TO}.0.x/adev/src/app/features/update/recommendations.ts`
- **Total items**: {TOTAL}
- **Audited**: {AUDITED} / {TOTAL}  ← MUST be 100%
- **Applied**: {APPLIED_COUNT}
- **Not applicable**: {NA_COUNT}
- **Runtime verified**: Yes / No (HTTP 200 from `ng serve`)

| # | Step ID | Level | Status | Notes |
|---|---------|-------|--------|-------|
| 1 | {step_id} | {Basic/Medium/Advanced} | {✅/🔧/⬜/❌} | {notes} |

## Breaking Changes Resolved

| # | Breaking Change | Resolution | Files Modified |
|---|----------------|------------|----------------|
| 1 | {description} | {how it was fixed} | {count} |

## Files Modified

| Type | Count |
|------|-------|
| .ts (components/services) | {n} |
| .spec.ts (tests) | {n} |
| .html (templates) | {n} |
| .scss (styles) | {n} |
| .json (config) | {n} |
| **Total** | **{n}** |

## Internal Packages

| Package | Old Version | New Version | Status |
|---------|------------|-------------|--------|
| {name} | {old} | {new} | Updated / Needs Republishing |

## Third-Party Dependencies (Phase 8B)

### Upgraded

| Package | Old → New | Reason |
|---------|-----------|--------|
| {name} | {old} → {new} | compatible with v{TO} / required for build |

### Deferred (compatible version needs deeper migration)

| Package | Current | Target (v{TO}-compatible) | Why deferred |
|---------|---------|---------------------------|--------------|
| {name} | {cur} | {target} | needs API-contract migration — couldn't finish in retry budget |

### At-risk

| Package | Current | Risk | Suggested action |
|---------|---------|------|------------------|
| {name} | {cur} | no v{TO} release / maintenance mode / EOL | pin / migrate to {alternative} |

## Deprecation Sweep

  {N} deprecated patterns replaced across {M} files

## SSR Status

- **SSR Detected**: Yes / No
- **Express Server**: {version}
- **SSR Migration Required**: Yes / No
- **Changes Made**: {description or "none"}
- **SSR server boot check**: PASS / FAIL / N/A (HTTP 200 + ng-version, clean server log)

## PM2 Configuration

- **PM2 Configs Found**: {N} (prod, stage, preprod)
- **Entry Point Valid**: Yes / No (`dist/server/server.mjs`)
- **Changes Required**: {description or "none"}

## Native Federation

- **Federated**: Yes / No
- **Role**: host / remote / host+remote / N/A
- **NF line**: v3→v3 / v3→v4 / v4→v4
- **Adapter**: `@angular-architects/native-federation[-v4]` {old} → {new}
- **Config migrated**: `federation.config.js` → `.mjs` (ESM) — Yes / No / N/A
- **SSR entry**: `fstart.mjs` (v20+) / `server.mjs` / N/A
- **Remotes load under CSP (runtime-verified)**: Yes / No / N/A
- **Remote inventory**: {list of remotes + whether in-repo or other-repo}
- **Cross-repo lockstep**: confirmed by user / not applicable (remote or in-repo) / **BLOCKED — remotes not upgraded**
- **Reconciled singleton pins**: {path to shared manifest} — {N} singletons pinned (Angular @ {exact patch}) / N/A
- **Shared-deps / singleton alignment**: matches reconciled pin across host + remotes / mismatch ({details})

## Post-Deploy Verification (Phase 10 — federated apps)

Runs in a later session, after this environment is deployed and **before promoting** it. Leave as
`NOT RUN` while the upgrade is pre-deploy — an empty section is honest, a missing one hides the gate.

- **Environment**: stage / prod       **Deployed at**: {timestamp}
- **Verdict**: PASS / PROMOTION BLOCKED / NOT RUN

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | Resolved shared set matches the reconciliation manifest | ✅/❌ | {N entries resolved by evaluating federation.config with node; drift vs manifest} |
| 2 | Live singleton skew sweep — **every** shared entry, not a shortlist | ✅/❌ | {pkg: v1 vs v2, across host + which remotes} |
| 3 | Cache headers: host `remoteEntry.json`, manifest, `index.html` all `no-cache`/`no-store` | ✅/❌ | {observed header values; absent header counts as a failure} |
| 4 | Warm-browser check in a profile that visited the previous deploy (never incognito) | ✅/❌ | {profile used, lazy routes exercised} |
| 5 | Blue/green promotion diff — only origins and genuinely new routes may differ | ✅/❌ | {expected-only / drift found} |

- **Non-strict singletons (`strictVersion: false`)**: {list} — these need *more* scrutiny than strict ones:
  a strict mismatch throws and announces itself, a non-strict one is silently substituted by
  highest-version-wins and passes a smoke test.
- **Any output from check 2 is a promotion blocker.** If promotion is blocked, state the rollback:
  `git reset --hard pre-angular-upgrade-v{TO} && {install-command}` (or redeploy the previous artifact).

## Build Status

- **Production build**: PASS / FAIL
- **Staging build**: PASS / FAIL
- **Build command**: `{command}`
- **Build-fix iterations**: {n}

## Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Production build time | {seconds} | build system: webpack / esbuild / native-federation |
| SSR dev-server start time | {seconds} / N/A | time to first HTTP 200 |

Flag any regression vs. the previous build system (e.g., native federation slower than webpack).

## Test Results

- **Total specs**: {n}
- **Passed**: {n}
- **Failed**: {n}
- **Skipped**: {n}
- **Test fixes applied**: {n}

### Coverage Comparison

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Statements | {%} | {%} | {+/-} |
| Branches | {%} | {%} | {+/-} |
| Functions | {%} | {%} | {+/-} |
| Lines | {%} | {%} | {+/-} |

## Lint Status

- **Lint-fix rounds**: {n}
- **Remaining lint errors**: {n}

## Remaining Issues

| # | Issue | Reason | Recommended Action |
|---|-------|--------|-------------------|
| 1 | {description} | {why it couldn't be fixed} | {suggested fix} |

## Phase Completion

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0: Pre-flight | Complete | - |
| Phase 1: Upgrade Plan | Complete | - |
| Phase 2: Baseline Check | Complete | - |
| Phase 3: Dependencies | Complete | - |
| Phase 3B: Migration Guide Audit | Complete | {AUDITED}/{TOTAL} items, {APPLIED} applied |
| Phase 4: SSR Migration | Complete / Skipped | - |
| Phase 5: Build Fix | Complete | {n} iterations |
| Phase 6: Lint Fix | Complete | {n} rounds |
| Phase 7: Deprecation Sweep | Complete | {n} patterns replaced |
| Phase 8: Test Fix | Complete | {n} fixes |
| Phase 8B: Third-Party Review | Complete / Skipped | {n} upgraded, {n} deferred |
| Phase 9: Validation | Complete | - |

## Node.js Compatibility

  Angular v{TARGET} requires Node.js v{min}.
  Current Node.js: v{current}   ← OK / WARNING

## Deployment Checklist

See `AI/deployment-checklist.md` (generated from `references/deployment-checklist.md`). Highlights:

- **Node.js**: Angular v{TARGET} requires Node v{min}. Server/CI images on v{current} → {OK / SRE must bump before deploy}.
- **Other env prerequisites**: {e.g., engines field, CI image, build memory}

## Rollback

- **Pre-upgrade commit**: {sha from `AI/upgrade-start-sha`}
- **Tag**: `pre-angular-upgrade-v{TO}` (local, not pushed)
- **To abandon this upgrade**: `git reset --hard pre-angular-upgrade-v{TO} && {install-command}`
- **Commits made by this run**: {n} (all `git add -A` — a plain revert of the last commit is not enough)
- **Published side effects**: {none / libraries published in library mode — list versions, these cannot be un-published}

## Effort Summary

- **Total phases completed**: {n}/10
- **Build-fix iterations**: {n}
- **Lint-fix rounds**: {n}
- **Test fixes applied**: {n}
- **Estimated AI contribution**: {%}
```
