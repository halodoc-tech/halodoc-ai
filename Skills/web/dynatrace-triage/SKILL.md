---
name: dynatrace-triage
version: "1.0.0"
maintainer: "halodoc-ai"
description: Senior Frontend Architect skill for high-confidence Dynatrace error diagnosis and durable remediation on any Angular/JS web frontend. Provides deep root-cause analysis, architecture-first fixes, confidence scoring, and reviewer-grade PR/MR rationale for client-side production errors. Operates in three modes — (1) single-error fix: trigger on "fix this Dynatrace error", "investigate this production error", or a specific error id; (2) strategic summary: trigger on "summarize our recurring Dynatrace errors", "rank our worst frontend crashes"; (3) auto-healing batch pipeline: trigger with "auto-heal", "batch fix Dynatrace errors", "remediate Dynatrace errors in batch" — live-pulls errors from the Dynatrace Error Inspector dashboard, hard-filters to 1st-party exceptions (>=100 users, 3-day window), shows a pre-fix plan, auto-fixes high-confidence errors with no approval, opens one Git MR per error. Scope: Dynatrace browser/client-side errors only — not backend 5xx/4xx, mobile crashes, or non-Dynatrace sources.
compatibility: Claude Code only — requires direct repo filesystem access and bash tools
---

# Dynatrace Triage

Provides a high-confidence fix or reviewer-grade triage for Dynatrace client-side errors on your web frontend.

## Configure for your project

This skill ships generic — nothing below is Halodoc-specific, but you must
supply your own values before running Mode 3:

| Setting | Where | Notes |
|---|---|---|
| Your site's domain(s) | `--first-party-domain` flag (required, no default) | Used for the hard 1st-party filter — see [eligibility.md](./references/eligibility.md) |
| Dynatrace app/frontend id | `--frontend` flag (Phase -1, [live-pull.md](./references/live-pull.md)) | The "Frontend" filter value in Dynatrace's Error Inspector |
| Sourcemap storage location | [sourcemaps.md](./references/sourcemaps.md) | Wherever your build pipeline deploys production `.js.map` files |
| Your route → module map | [module-map.md](./references/module-map.md) | Build this once from your own routing config |

## What This Skill Emphasizes

- prioritize root cause over symptom suppression
- require explicit `symptom`, `trigger`, and `root_cause`
- use source/fix confidence before auto-delivery
- produce a consistent reviewer-facing MR body

## Scope

Dynatrace-sourced browser/client-side errors only. This skill does NOT
handle: backend 5xx/4xx (a separate skill should own that), native mobile
crashes, or errors from a monitoring source other than Dynatrace.

**Limitations:**
- GitLab-only for MR creation (`glab`) with a GitHub (`gh`) fallback — no
  Bitbucket support.
- Requires Python 3, bash, and git; the `glab`/`gh` CLI is optional (its
  absence is a recorded blocker, not a hard stop).
- The live-pull depends on the Dynatrace Error Inspector Explorer's current
  UI shape ([live-pull.md](./references/live-pull.md)), which may change
  without notice between Dynatrace releases — locate elements fresh each run
  rather than hardcoding coordinates/selectors. There is no CSV or API-token
  fallback; Mode 3 requires an interactive Claude Code session with Chrome
  browser access.
- The 75% remediation target is a heuristic default, not a hard
  requirement — adjust to your team's SLA.
- **Sourcemap unavailability:** if production sourcemaps are disabled by
  policy and can't be enabled (see [sourcemap-preflight.md](./references/sourcemap-preflight.md)),
  source localization falls back to heuristics (minified function names,
  chunk-URL module inference, page-routing correlation). Confidence scores
  trend lower — expect more `low source confidence` / report-only outcomes.
  If your Dynatrace plan offers a "deobfuscated stack trace" export option,
  use that as the best workaround.

## Progressive Loading

Keep this file as the orchestrator. Load only the extra files you need.

| Resource | Lines | When to load |
|---|---|---|
| [workflow.md](./references/workflow.md) | 168 | Mode 1/2 end-to-end flow |
| [architecture-rules.md](./references/architecture-rules.md) | 87 | Fix selection and confidence scoring |
| [mr-format.md](./references/mr-format.md) | 160 | The canonical MR body format |
| [error-patterns.md](./references/error-patterns.md) | 239 | Common Angular error patterns and source mapping hints |
| [module-map.md](./references/module-map.md) | 26 | Module/page routing hints |
| [sourcemaps.md](./references/sourcemaps.md) | 106 | Deobfuscating minified `<your-domain>/resources/*.js` frames |
| [auto-heal-workflow.md](./references/auto-heal-workflow.md) | 394 | Mode 3 batch pipeline (load early for any heal run) |
| [eligibility.md](./references/eligibility.md) | 120 | Auto-heal targeting rules (users threshold, hard 1st/3rd-party filter) |
| [live-pull.md](./references/live-pull.md) | 123 | Pulling errors live via an authenticated Chrome session — the only Mode 3 acquisition path |
| [visualization.md](./references/visualization.md) | 89 | The pre-fix triage board and post-run fixed/not-fixed board — rendered as Claude Code HTML Artifacts, redeployed to the same URL between the pre- and post-run render |
| [sourcemap-preflight.md](./references/sourcemap-preflight.md) | 53 | Checking/enabling production sourcemaps — a read/write check: no-op if already enabled, else its own dedicated branch/MR (never mixed into an error-fix branch) |
| [registry-format.md](./references/registry-format.md) | 104 | The attribution registry schema and run report |
| [parser.py](./scripts/parser.py) | — | CSV parsing or reusable row extraction |
| [eligibility.py](./scripts/eligibility.py) | — | Auto-heal work-queue filtering |
| [registry.py](./scripts/registry.py) | — | Attribution registry init/update/report/verify |
| [scripts/README.md](./scripts/README.md) | 77 | Script usage and error-handling conventions — Python 3 stdlib only, no `pip install` needed |
| [evals.json](./evals/evals.json) / [sample_errors.csv](./evals/sample_errors.csv) | — | Sample eval prompts and expected behavior — only when validating the skill itself |

**Note:** every reference file ≥100 lines includes a `## Contents` section at the top for partial-read navigation (applied consistently at the 100-line boundary, e.g. `registry-format.md` at 104 lines). Scripts (`.py`) are excluded from this rule and from the line-count column (`—`) — their size isn't a stable/meaningful metric and they're read via `grep`/targeted sections, not top-to-bottom.

## Operating Rules

- Act as a senior frontend architect.
- Do not stop at the first plausible patch.
- Prefer restoring the correct invariant over adding a null guard.
- Never claim the root cause is fixed unless the contract/lifecycle/state issue is addressed.
- Never edit vendor files, `dist/`, `node_modules/`, or generated output.
- Auto-apply, commit, push, and open an MR only when source confidence is not low and fix confidence is high or medium with explicit assumptions.
- In heal mode (Mode 3), the confidence rule IS the approval gate for **Claude Code users** — never prompt the human for eligible high-confidence fixes **once the fixing phase (Phase 2B) begins**; the only allowed stop is a dirty git tree. The pre-fix visualization (Phase 2A's "Visualize" step) does not wait for a human "go ahead" either — it's Claude's own sanity-check pass over the board before proceeding straight to Phase 2B; the human watching the session retains ambient ability to interrupt, but the workflow itself never blocks on a confirmation prompt at any point except `--dry-run`, which stops after the visualization deliberately. After Phase 2B begins, confidence scores alone decide whether a fix auto-merges, with no per-fix prompts. **Sequencing exception for IDE/restricted users**: the Portability Note workaround has users manually run eligibility filtering and PREVIEW the work queue before starting the fixing phase inside Claude Code — that preview is a deliberate planning step required by the environment's restrictions, not a contradiction of "no approval during fixing" (which describes the fixing phase's behavior once started, whether reached via full auto-orchestration or the manual-preview workaround).
- In heal mode, one error's failure never aborts the batch: record it in the registry, reset to clean master, continue.
- In heal mode, every auto-fixed error must produce exactly one MR from a branch provably cut from latest `origin/master`, and every non-fixed eligible error must appear in the run report with a triage writeup. Never widen the confidence gate to reach the remediation-rate target.

**Auto-heal tradeoff:** Mode 3's "confidence gate replaces human approval" design trades pre-merge review for speed and scale. The requirements that make this safe:
- **Source confidence** ≥ medium: ≥2 aligned signals (function name, module, error property match) localize the source file with high probability.
- **Fix confidence** ≥ medium: the fix restores a documented invariant (not a blind null guard) and includes a test reproducing the failure path.
- **Post-merge verification** (see Delivery Expectations below): required Dynatrace queries at 15-60 min and across 7 days catch regressions — a fix that doesn't reduce affected-user counts is reopened.
- **Rollback procedure** (see Rollback Procedure section): a defined revert path exists for merged fixes that worsen production.

If your team's SLA requires human review for ALL prod changes, use `--dry-run` to stop after the pre-fix visualization (Phase 2A), review the board, then manually invoke fixes one-by-one in Mode 1 instead of batch Mode 3.

- In heal mode, 1st-party is a HARD filter applied before anything else — 3rd-party errors (ad/analytics scripts, browser extensions, opaque cross-origin) never enter the fix queue on a "suspected" basis, but they are still shown (excluded, with reason) on the pre-fix visualization for auditability.
- `--first-party-domain` takes a bare domain (e.g. `<your-domain>`, no protocol) and matches by **suffix** — `<your-domain>` matches `<your-domain>` itself and any subdomain (`www.<your-domain>`, `app.<your-domain>/resources/chunk.js`), but not unrelated domains that merely contain the string. Pass the flag multiple times to allow multiple first-party domains in one run (e.g. `--first-party-domain <your-domain> --first-party-domain <another-domain>`).
- **Branch conflict handling:** if two fixes in the same run would modify the same file, their MRs could conflict. Before branching for an error, run `scripts/registry.py check-files --run-id <run> --error-id <id> --files <comma-separated planned files>` against the errors already `auto-fixed` this run. On conflict (nonzero exit), mark the error `deferred-conflict` (`registry.py update ... --status deferred-conflict --note "conflicts with <other error id> on <file>"`) and skip it this run — it re-enters the queue on the next auto-heal run once the conflicting MR has merged. This trades same-run parallelism for merge safety; it does not attempt to reconcile the two fixes automatically. Full protocol: [auto-heal-workflow.md](./references/auto-heal-workflow.md) Phase 2B.
- In heal mode, never touch Dynatrace before Phase -1's `--frontend` and `--first-party-domain` values are resolved — ask if not specified.
- Re-run safety: before branching, the skill checks whether the error ID already has an open or merged MR recorded in the registry; if so, the error is skipped — its existing status (`auto-fixed`/`auto-fixed-mr-pending`/etc.) is left unchanged and a note is appended (e.g. "skipped: already has an open MR from a prior run"), it is not relabeled to a separate "duplicate" status. `reverted`/`reopened`/`deferred-conflict` entries are the exception — those are re-processed, not skipped (see [auto-heal-workflow.md](./references/auto-heal-workflow.md) Phase 2B's re-run dedupe for full logic).
- Never use `innerHTML`, `outerHTML`, `dangerouslySetInnerHTML`, `bypassSecurityTrustHtml`, or `eval()`/`new Function()` in a fix — use safe alternatives (`textContent`, `DomSanitizer`, framework-native rendering) or explicitly document why the risk is unavoidable. Full detail: [architecture-rules.md](./references/architecture-rules.md)'s Security Constraints.
- If the target repo uses SSR (Angular Universal, Next.js, etc.), ensure fixes avoid browser-only APIs (`window`, `document`, `localStorage`) in SSR-executed code paths — guard with `isPlatformBrowser`/`typeof window !== 'undefined'` or a client-only lifecycle hook.
- Prefer fixing the root invariant over adding a heavy defensive dependency — a null guard is fine; importing a utility library for one helper call is not. If a fix genuinely needs a new dependency, justify the bundle-size impact in the MR body.
- Most root-cause fixes are logic-only (restoring an invariant, guarding a lifecycle race) and touch no UI. On the rarer fix that does add or modify UI (an error boundary's fallback content, a loading state): use the project's existing design system/component library over ad-hoc HTML/CSS; keep it accessible (semantic elements, ARIA labels where needed, working keyboard navigation, focus management for any modal/dialog); and route any new user-facing text through the project's i18n system rather than hardcoding a string.

## Portability Note

This skill requires Claude Code (desktop/CLI) — it needs direct filesystem
access, bash tools, and to run the bundled Python scripts. It will NOT work
in the Claude.ai web UI or in IDE extensions with restricted script
execution.

**Workaround for IDE/restricted-environment users**: Mode 3's live-pull step
itself has no substitute — it requires `claude-in-chrome` tools inside a
Claude Code session, full stop. What CAN run outside Claude Code is the
eligibility-filtering script, if you hand-build the row list yourself (copy
the Error Name/Affected Users/etc. columns visible in the Dynatrace Error
Inspector Explorer UI into a JSON file matching the schema below) — this
needs **two separate environments**: any shell with Python 3 for filtering,
and a separate Claude Code session (desktop app or CLI) for the
diagnosis/fix/MR phase:

```bash
# Linux/macOS:
cd /path/to/your/frontend-repo
python3 /path/to/dynatrace-triage/scripts/eligibility.py rows.json \
  --first-party-domain <your-domain> --min-users 100 --out queue.json

# Windows — PowerShell (uses backtick ` for line continuation, shown below):
cd /c/path/to/your/frontend-repo
python3 /c/path/to/dynatrace-triage/scripts/eligibility.py rows.json `
  --first-party-domain <your-domain> --min-users 100 --out queue.json

# Windows — Git Bash/WSL (uses backslash \ for line continuation, like Linux/macOS):
cd /c/path/to/your/frontend-repo
python3 /c/path/to/dynatrace-triage/scripts/eligibility.py rows.json \
  --first-party-domain <your-domain> --min-users 100 --out queue.json
```

**Path portability note:** every path in this skill uses forward slashes
(`/`), which work on Linux, macOS, WSL, Git Bash, and PowerShell. This
skill requires Claude Code (which runs bash), so native `cmd.exe` isn't a
supported shell here — use PowerShell, Git Bash, or WSL on Windows. The
backtick (`` ` ``) in the PowerShell example above is that shell's line-continuation
syntax, not part of the path — Git Bash/WSL use a trailing backslash (`\`)
instead, as shown.

Then invoke this skill in Claude Code, pointing it at `queue.json`, for the
diagnosis/fix/MR phase.

This gives restricted-environment users the eligibility-filtering and
registry tooling even when the live-pull and full auto-fix orchestration
require Claude Code.

## Row Schema

`scripts/eligibility.py` takes a JSON row list (a bare list, or `{"rows": [...]}`) — this is what [live-pull.md](./references/live-pull.md) must emit from the Explorer, and what a manual restricted-environment workaround must hand-author:

| Key | Description |
|--------|-------------|
| `error_id` | Stable id for the error — the Explorer UI doesn't expose one directly, so live-pull derives it (e.g. a short hash of the normalized error text); it just needs to be stable across runs so dedupe/re-run logic works |
| `error_text` | The exception name/message (the Explorer's "Error Name" column) |
| `severity` | Dynatrace-assigned severity, if available |
| `signal` | Dynatrace's own signal/confidence label, if available |
| `users` | Count of unique affected users in the pulled window |
| `count` | Total occurrence count |
| `teams` | Team(s) Dynatrace attributes the error to, if tagged |
| `top_pages` | Pages where the error occurred most |
| `browsers` | Browsers where the error occurred |

Only `error_id`, `error_text`, and `users` are required for the eligibility classification pass; the rest may be empty strings and get filled in later, per-candidate, from the row's detail drill-down (Phase 2A diagnosis).

**Fallback:** If the JSON is malformed or not a list, `eligibility.py` fails at parse time with a clear message naming the problem.

## Confidence Scoring (Summary)

The full rubric — the only canonical definition — lives in [architecture-rules.md](./references/architecture-rules.md)'s Confidence Model. This table is a pointer, not a duplicate, to avoid the two drifting apart:

| Confidence | Source (one-line) | Fix (one-line) |
|---|---|---|
| **High** | ≥2 independent signals point to the same file/component | Root cause is coherent, minimal fix is clear, tests can cover it |
| **Medium** | 1 strong signal, mapping incomplete | Plausible but architectural cause is partly inferred |
| **Low** | Vague/indirect clues, vendor/minified stack dominates | Speculative or merely suppressive |

**Auto-fix gate (Mode 3)**: high source + high fix, OR medium source +
medium fix with explicit assumptions written into the MR and registry. Low
confidence on either axis → report-only, never a guess. Full rubric and
fix-hierarchy: [architecture-rules.md](./references/architecture-rules.md).

**Example**: error `Cannot read properties of undefined (reading 'push')`
at `<your-domain>/resources/chunk-123.js:5:234`. The stack shows function
name `navigateToCart`, the top page is `/cart`, and the error property
(`push`) matches a router/history operation. That's 2 aligned signals
(function name + page routing) → **high source confidence**. The fix
restores the router's initialization in the cart page's lifecycle, with a
test reproducing the crash → **high fix confidence** → eligible for
auto-fix.

## Modes

### Mode 1: High-Confidence Fix

Command pattern: `dynatrace_triage {{error_id}}`

Read these before acting:
- [workflow.md](./references/workflow.md)
- [architecture-rules.md](./references/architecture-rules.md)
- [mr-format.md](./references/mr-format.md)

Then:
1. Parse the exact CSV row.
2. Build evidence before patching.
3. Locate the source with at least 2 aligned signals when possible.
4. Diagnose `symptom`, `trigger`, and `root_cause`.
5. Apply the smallest correct fix with focused tests.
6. Use the canonical MR body format from [mr-format.md](./references/mr-format.md).

### Mode 2: Strategic Summary

Command pattern: `dynatrace_triage summary`

Read these before acting:
- [workflow.md](./references/workflow.md)
- [architecture-rules.md](./references/architecture-rules.md)
- [error-patterns.md](./references/error-patterns.md)

Then:
1. Rank the errors.
2. Group duplicates and likely-shared causes.
3. Identify architectural patterns.
4. Recommend a prioritized remediation roadmap.

### Mode 3: Auto-Heal Batch

Trigger phrases: "auto-heal", "batch fix Dynatrace errors", "fix all Dynatrace errors", "remediate Dynatrace errors in batch" ("heal" with **no other context** — i.e. the single word alone — is deliberately NOT a trigger, too ambiguous in health-related products; but "heal these errors", "heal the Dynatrace issues", or "heal the cart page crashes" all carry enough context to trigger Mode 3 like the phrases above).

**Mode disambiguation:** a phrase like "fix all errors" could plausibly mean Mode 1 (a single error literally named "all") or Mode 3 (batch). Check for Mode 3 keywords first (above); if none are present AND no `--frontend` flag or batch-scale context (multiple error IDs) is given, ask: "Do you mean fixing a single error, or batch-fixing all errors via auto-heal?" — Mode 3 is the higher-stakes, no-approval operation, so confirm before proceeding on an ambiguous phrase.

Command pattern: `dynatrace_triage heal --frontend <frontend-id> --first-party-domain <domain> [--repo <path>] [--min-users 100] [--dry-run]`

**CI users:** set `REGISTRY_PATH=/workspace/registry.json` (or any
persistent path) to override the default `~/.claude/…` location, which
doesn't survive an ephemeral CI home.

Read these before acting:
- [auto-heal-workflow.md](./references/auto-heal-workflow.md)
- [live-pull.md](./references/live-pull.md)
- [eligibility.md](./references/eligibility.md)
- [visualization.md](./references/visualization.md)
- [architecture-rules.md](./references/architecture-rules.md)
- [mr-format.md](./references/mr-format.md)

Then:
1. **Phase -1**: resolve `--frontend` and `--first-party-domain` (ask if
   either isn't specified) and confirm a Chrome session with tenant access
   is available — BEFORE touching Dynatrace. There is no other acquisition
   path to choose between; Mode 3 always live-pulls via
   [live-pull.md](./references/live-pull.md).
2. Run Phase 0 preconditions: verify Python 3 is available (`python3 --version`; if not found, tell the user "Python 3 is required but not installed — install it or run in an environment where it's available" and stop), clean tree, latest master, sourcemap preflight, registry init.
3. Pull errors via the chosen path (3-day window), build the work queue with `scripts/eligibility.py` (hard 1st-party filter, then threshold), register every row. **If the queue is empty after filtering** (every row was 3rd-party or below the users threshold), print "No eligible errors found — 0 errors passed the 1st-party filter and min-users threshold. Nothing to fix." and exit cleanly — do not create registry entries beyond the `init` record, do not render the visualization, and do not proceed to Phase 2A/2B.
4. **Phase 2A**: diagnose every eligible error (evidence, confidence, planned action) with no side effects yet.
5. **Visualize**: render the pre-fix triage board (Artifact) showing every candidate's plan, plus excluded/skipped rows for audit. **"Last chance to review" means Claude's own sanity-check pass, not a wait-for-human-confirmation step** — inspect the board, sanity-check the confidence scores and planned actions against the evidence gathered in Phase 2A, then proceed directly to Phase 2B without pausing for a human "go ahead." (Because this runs inside an interactive Claude Code session, the human watching can still interrupt at any point — that's ambient oversight, not a formal gate the workflow waits on.) Use `--dry-run` to stop here without executing anything — that is the only flag that halts the pipeline at this point.
6. **Phase 2B**: execute the planned actions — confidence gate replaces the human approval prompt; low confidence → report-only; high/medium-with-assumptions → branch/fix/test/MR.
7. Finalize: `scripts/registry.py finalize` + `report`, redeploy the visualization as the post-run board, print the run report with the 75%-target verdict (a heuristic — high-confidence fixes should resolve roughly 3/4 of eligible-user-volume; adjust to your team's SLA if 75% isn't the right bar).
8. Never ask for approval unless the git tree is dirty; `glab` missing is a recorded blocker, not a stop.

## Worked Example — Mode 3 Auto-Heal

**Scenario:** 3 rows live-pulled from the Error Inspector Explorer (3-day window, `--frontend <your-frontend> --first-party-domain <your-domain> --min-users 100`).

**Live-pulled rows (relevant fields):**

| `error_id` | `error_text` | `users` | Top stack frame |
|---|---|---|---|
| ERR-A1 | Cannot read properties of undefined (reading 'push') | 250 | `<your-domain>/resources/chunk-cart.js:5:234` (`navigateToCart`) |
| ERR-D4 | TypeError: Cannot read 'length' | 80 | `<your-domain>/resources/chunk-search.js:12:100` |
| ERR-G7 | Script error. | 300 | `some-ad-network.example/tracker.js:1:1` |

**Eligibility filter (`scripts/eligibility.py --first-party-domain <your-domain> --min-users 100`):**
- ERR-A1: 1st-party, 250 ≥ 100 users → **eligible**
- ERR-D4: 80 < 100 users → **excluded** (`skipped-below-threshold`)
- ERR-G7: 3rd-party domain → **excluded** (`skipped-3rd-party`, hard filter)

**Work queue:** 1 error (ERR-A1).

**Phase 2A diagnosis:**
- Source confidence **high** — 2 aligned signals: function name `navigateToCart` + page routing to `/cart`.
- Fix confidence **high** — root cause is a router not re-initialized in the cart page's lifecycle; fix restores the init call; a test reproduces the crash.
- Planned action: **auto-fix**.

**Phase 2B execution:**
- Branch `fix/error-ERR-A1-cart-router`, cut from latest `origin/master`.
- Commit restores the router init in the cart page lifecycle hook, adds a focused regression test.
- MR opened: "Fix ERR-A1: cart page router undefined on re-entry".
- `registry.py update --status auto-fixed --mr-url <url> --branch fix/error-ERR-A1-cart-router ...`

**Run report:** Auto-fixed 1/1 eligible (250/250 users = 100% remediation, exceeds the 75% target); 2 excluded (3rd-party, below threshold) listed with reasons; MR coverage 100%.

**Post-merge verification (15-60 min):** query `error.id = "ERR-A1"` in Error Inspector → `👥 Users` trending to 0 → fix confirmed, no rollback needed.

## Delivery Expectations

Before proposing delivery, verify:
- **Build succeeds**: `pnpm build` (or `ng build --configuration=production` / `tsc --noEmit` — whichever the project provides) completes without errors
- **Lint passes**: `pnpm eslint <changed files>` shows no new violations
- **Tests pass**: the focused spec covering the failure path is green

Then, always be able to answer:
- What was the runtime symptom?
- What exact path triggered it?
- What is the actual root cause?
- Why is this fix better than a defensive band-aid?
- What regression risk remains?
- What test proves the failure path is covered?

If those answers are weak, continue investigating instead of acting certain.

Additionally, in heal mode (Mode 3), a run is only complete when:
- the run report is printed with the remediation rate vs the 75% target and an explicit verdict
- every auto-fixed error has an MR URL (or a recorded `glab mr create` blocker) — MR coverage must be 100%
- every eligible-but-unfixed error has a triage writeup in the registry
- the registry is finalized and the pulled row count reconciles across auto-fixed / reported / skipped tables

**Post-merge verification is required to confirm impact reduction** — an
`auto-fixed` status is a claim (tests + build passed locally) until
confirmed in production, not a completed outcome. Query Dynatrace again
~15-60 minutes after the MRs deploy, and again across the following 7 days,
to confirm affected-user counts actually dropped. If counts remain stable
or increase, reopen the error for deeper investigation — the fix may have
been a symptom patch, not a root-cause resolution. See
[auto-heal-workflow.md](./references/auto-heal-workflow.md) Phase 4 for the
full verification protocol.

**How to verify (manual protocol):**
1. **15-60 min after deploy:** In Dynatrace Error Inspector → Explorer, filter to the error IDs from this run's report (the `error.id` values in the Auto-Fixed table). Check the `👥 Users` column for each — counts should be dropping toward zero. If any is stable or increasing, treat it as a rollback candidate (see Rollback Procedure below).
2. **7 days after deploy:** Repeat the same filtered query with a 7-day window. Confirm the downward trend held. If not, `registry.py update --run-id <run> --error-id <id> --status reopened --note "<what the 7-day query showed>"`.

**This verification is intentionally manual**, not a missing automation.
Trend interpretation (stable vs. dropping vs. spiking affected-user counts)
requires human judgment that a script would either get wrong or need to be
as conservative as a human anyway; automating the Dynatrace queries would
also add credential/retry complexity for a step that already has a clear,
low-effort manual protocol. Set a calendar reminder for the 15-60 min and
7-day checks against the error IDs in the run report.

## Rollback Procedure

If post-merge verification shows affected-user counts stable or increasing
after a fix MR merges:

1. **Revert**: `git revert -m 1 <merge-commit-sha>`, fast-track the revert
   through review. `registry.py update … --status reverted --note "<why>"`.
2. **Re-analyze**: `registry.py update … --status reopened --note "<what verification showed>"`
   — the original fix was a symptom patch. Return to Phase 2A with deeper
   evidence (reproduce locally, profile, re-check lifecycle assumptions)
   rather than re-running the same diagnosis.
3. **Forensics**: compare the reverted fix's changed files against the
   error's stack frames — if the fix touched a file the stack trace never
   named, source confidence was overestimated; tighten the confidence gate
   before the next attempt.

A `reverted` or `reopened` entry is excluded from future re-run dedupe — it
will be re-processed on the next heal run rather than silently skipped as
"already fixed." Full step-by-step protocol: [auto-heal-workflow.md](./references/auto-heal-workflow.md) Phase 4.
