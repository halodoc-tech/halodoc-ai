---
name: dynatrace-triage
version: "1.0.0"
maintainer: "halodoc-ai"
description: Senior Frontend Architect skill for high-confidence Dynatrace CSV diagnosis and durable remediation on any Angular/JS web frontend. Use when you want deep root-cause analysis, architecture-first fixes, stronger regression thinking, evidence-based confidence scoring, and reviewer-grade PR/MR rationale for client-side production errors. Also supports an auto-healing batch pipeline — trigger with "heal", "auto-heal", or "batch fix Dynatrace errors" — that pulls errors live from Dynatrace (Chrome browser session or API token — asks which) or from a CSV export, hard-filters to 1st-party exceptions (>=100 users, rolling 7-day window), shows a readable pre-fix plan before touching any code, fixes with no approval prompt, opens one Git MR per fixed error, and tracks the full fix lifecycle in an attribution registry.
compatibility: Claude Code only — requires direct repo filesystem access and bash tools
---

# Dynatrace Triage

Use this skill when the user wants a high-confidence fix or reviewer-grade triage for Dynatrace client-side errors on your web frontend.

## Configure for your project

This skill ships generic — nothing below is Halodoc-specific, but you must
supply your own values before running Mode 3:

| Setting | Where | Notes |
|---|---|---|
| Your site's domain(s) | `--first-party-domain` flag (required, no default) | Used for the hard 1st-party filter — see [eligibility.md](./references/eligibility.md) |
| Dynatrace app/frontend id | Phase -1 source pull ([live-pull.md](./references/live-pull.md) / [token-pull.md](./references/token-pull.md)) | The "Frontend" filter value in Dynatrace's Error Inspector |
| `DT_API_TOKEN` (optional) | your shell / CI secret | Only needed for the token/DQL acquisition path; scope `storage:query:read` |
| Sourcemap storage location | [sourcemaps.md](./references/sourcemaps.md) | Wherever your build pipeline deploys production `.js.map` files |
| Your route → module map | [module-map.md](./references/module-map.md) | Build this once from your own routing config |

## What This Skill Emphasizes

- prioritize root cause over symptom suppression
- require explicit `symptom`, `trigger`, and `root_cause`
- use source/fix confidence before auto-delivery
- produce a consistent reviewer-facing MR body

## Progressive Loading

Keep this file as the orchestrator. Load only the extra files you need.

- For the end-to-end workflow: read [workflow.md](./references/workflow.md)
- For fix selection and confidence scoring: read [architecture-rules.md](./references/architecture-rules.md)
- For the canonical MR body format: read [mr-format.md](./references/mr-format.md)
- For common Angular error patterns and source mapping hints: read [error-patterns.md](./references/error-patterns.md)
- For module/page hints: read [module-map.md](./references/module-map.md)
- For minified `<your-domain>/resources/*.js` frames that need deobfuscation: read [sourcemaps.md](./references/sourcemaps.md)
- For the auto-heal batch pipeline (Mode 3): read [auto-heal-workflow.md](./references/auto-heal-workflow.md)
- For auto-heal targeting rules (users threshold, hard 1st/3rd-party filter): read [eligibility.md](./references/eligibility.md)
- For pulling errors live via an authenticated Chrome session: read [live-pull.md](./references/live-pull.md)
- For pulling errors live via `DT_API_TOKEN`/DQL: read [token-pull.md](./references/token-pull.md)
- For the pre-fix triage board and post-run fixed/not-fixed board: read [visualization.md](./references/visualization.md)
- For checking/enabling production sourcemaps in any web project: read [sourcemap-preflight.md](./references/sourcemap-preflight.md)
- For the attribution registry schema and run report: read [registry-format.md](./references/registry-format.md)
- For CSV parsing or reusable row extraction: use [parser.py](./scripts/parser.py)
- For auto-heal work-queue filtering: use [eligibility.py](./scripts/eligibility.py)
- For attribution registry init/update/report/verify: use [registry.py](./scripts/registry.py)
- For quick script usage notes: read [README.md](./scripts/README.md)
- For sample eval prompts and expected behavior baselines: inspect [evals.json](./evals/evals.json) and [sample_errors.csv](./evals/sample_errors.csv) only when validating the skill itself

## Operating Rules

- Act as a senior frontend architect.
- Do not stop at the first plausible patch.
- Prefer restoring the correct invariant over adding a null guard.
- Never claim the root cause is fixed unless the contract/lifecycle/state issue is addressed.
- Never edit vendor files, `dist/`, `node_modules/`, or generated output.
- Auto-apply, commit, push, and open an MR only when source confidence is not low and fix confidence is high or medium with explicit assumptions.
- In heal mode (Mode 3), that confidence rule IS the approval gate — never prompt the human for eligible high-confidence fixes; the only allowed human stop is a dirty git tree.
- In heal mode, one error's failure never aborts the batch: record it in the registry, reset to clean master, continue.
- In heal mode, every auto-fixed error must produce exactly one MR from a branch provably cut from latest `origin/master`, and every non-fixed eligible error must appear in the run report with a triage writeup. Never widen the confidence gate to reach the remediation-rate target.
- In heal mode, 1st-party is a HARD filter applied before anything else — 3rd-party errors (ad/analytics scripts, browser extensions, opaque cross-origin) never enter the fix queue on a "suspected" basis, but they are still shown (excluded, with reason) on the pre-fix visualization for auditability.
- In heal mode, never touch Dynatrace before Phase -1's data-source choice (token vs. browser vs. CSV) is resolved — ask if not specified.

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

Command pattern: `dynatrace_triage heal [--csv <path> | --source token|browser] [--repo <path>] [--min-users 100] [--dry-run]`

Read these before acting:
- [auto-heal-workflow.md](./references/auto-heal-workflow.md)
- [live-pull.md](./references/live-pull.md) / [token-pull.md](./references/token-pull.md) (per chosen source)
- [eligibility.md](./references/eligibility.md)
- [visualization.md](./references/visualization.md)
- [architecture-rules.md](./references/architecture-rules.md)
- [mr-format.md](./references/mr-format.md)

Then:
1. **Phase -1**: resolve the data source (CSV given → use it; else `--source` or ask token vs. browser) BEFORE touching Dynatrace.
2. Run Phase 0 preconditions (clean tree, latest master, sourcemap preflight, registry init).
3. Pull errors via the chosen path (7-day window), build the work queue with `scripts/eligibility.py` (hard 1st-party filter, then threshold), register every row.
4. **Phase 2A**: diagnose every eligible error (evidence, confidence, planned action) with no side effects yet.
5. **Visualize**: render the pre-fix triage board (Artifact) showing every candidate's plan, plus excluded/skipped rows for audit — this is a preview only.
6. **Phase 2B**: execute the planned actions — confidence gate replaces the human approval prompt; low confidence → report-only; high/medium-with-assumptions → branch/fix/test/MR.
7. Finalize: `scripts/registry.py finalize` + `report`, redeploy the visualization as the post-run board, print the run report with the 75%-target verdict.
8. Never ask for approval unless the git tree is dirty; `glab` missing is a recorded blocker, not a stop.

## Delivery Expectations

Before proposing delivery, always be able to answer:
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
- the registry is finalized and the CSV row count reconciles across auto-fixed / reported / skipped tables
