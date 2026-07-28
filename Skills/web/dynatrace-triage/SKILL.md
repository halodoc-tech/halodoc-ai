---
name: dynatrace-triage
version: "1.0.0"
maintainer: "halodoc-ai"
description: Senior Frontend Architect skill for high-confidence Dynatrace error diagnosis and durable remediation on any Angular/JS web frontend. Provides deep root-cause analysis, architecture-first fixes, stronger regression thinking, evidence-based confidence scoring, and reviewer-grade PR/MR rationale for client-side production errors — trigger on "fix this Dynatrace error", "why is this Dynatrace crash happening", "investigate this production error", or a specific error id. Also supports a strategic summary mode — trigger on "summarize our recurring Dynatrace errors", "rank our worst frontend crashes", "remediation roadmap for these errors". Also supports an auto-healing batch pipeline — trigger with "auto-heal", "batch fix Dynatrace errors", "fix all Dynatrace errors", or "remediate Dynatrace errors in batch" (bare "heal" alone is deliberately NOT a trigger — too ambiguous, especially in health-related products) — that pulls errors live from Dynatrace (Chrome browser session or API token — asks which) or from a CSV export, hard-filters to 1st-party exceptions (>=100 users, rolling 7-day window), shows a readable pre-fix plan before touching any code, fixes with no approval prompt, opens one Git MR per fixed error, and tracks the full fix lifecycle in an attribution registry. Scope: Dynatrace-sourced browser/client-side errors only — not backend 5xx/4xx, not native mobile crashes, not non-Dynatrace error sources.
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
| Dynatrace app/frontend id | Phase -1 source pull ([live-pull.md](./references/live-pull.md) / [token-pull.md](./references/token-pull.md)) | The "Frontend" filter value in Dynatrace's Error Inspector |
| `DT_API_TOKEN` (optional) | your shell / CI secret | Only needed for the token/DQL acquisition path; scope `storage:query:read` |
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

## Progressive Loading

Keep this file as the orchestrator. Load only the extra files you need.

| Resource | Lines | When to load |
|---|---|---|
| [workflow.md](./references/workflow.md) | 163 | Mode 1/2 end-to-end flow |
| [architecture-rules.md](./references/architecture-rules.md) | 87 | Fix selection and confidence scoring |
| [mr-format.md](./references/mr-format.md) | 152 | The canonical MR body format |
| [error-patterns.md](./references/error-patterns.md) | 239 | Common Angular error patterns and source mapping hints |
| [module-map.md](./references/module-map.md) | 26 | Module/page routing hints |
| [sourcemaps.md](./references/sourcemaps.md) | 106 | Deobfuscating minified `<your-domain>/resources/*.js` frames |
| [auto-heal-workflow.md](./references/auto-heal-workflow.md) | 380 | Mode 3 batch pipeline (load early for any heal run) |
| [eligibility.md](./references/eligibility.md) | 120 | Auto-heal targeting rules (users threshold, hard 1st/3rd-party filter) |
| [live-pull.md](./references/live-pull.md) | 123 | Pulling errors live via an authenticated Chrome session |
| [token-pull.md](./references/token-pull.md) | 135 | Pulling errors live via `DT_API_TOKEN`/DQL |
| [visualization.md](./references/visualization.md) | 89 | The pre-fix triage board and post-run fixed/not-fixed board — rendered as Claude Code HTML Artifacts, redeployed to the same URL between the pre- and post-run render |
| [sourcemap-preflight.md](./references/sourcemap-preflight.md) | 53 | Checking/enabling production sourcemaps — a read/write check: no-op if already enabled, else its own dedicated branch/MR (never mixed into an error-fix branch) |
| [registry-format.md](./references/registry-format.md) | 104 | The attribution registry schema and run report |
| [parser.py](./scripts/parser.py) | — | CSV parsing or reusable row extraction |
| [eligibility.py](./scripts/eligibility.py) | — | Auto-heal work-queue filtering |
| [registry.py](./scripts/registry.py) | — | Attribution registry init/update/report/verify |
| [scripts/README.md](./scripts/README.md) | 77 | Script usage and error-handling conventions — Python 3 stdlib only, no `pip install` needed |
| [evals.json](./evals/evals.json) / [sample_errors.csv](./evals/sample_errors.csv) | — | Sample eval prompts and expected behavior — only when validating the skill itself |

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
- Re-run safety: the registry prevents duplicate MRs — if an error already has an open MR from a prior run, it is skipped rather than re-fixed (see [auto-heal-workflow.md](./references/auto-heal-workflow.md) Phase 2B's re-run dedupe).
- Never echo `DT_API_TOKEN` values in logs, error messages, or MR bodies — if a token-related operation fails, report "token rejected" / "authentication failed", never the token itself.

## Portability Note

This skill requires Claude Code (desktop/CLI) — it needs direct filesystem
access, bash tools, and to run the bundled Python scripts. It will NOT work
in the Claude.ai web UI or in IDE extensions with restricted script
execution.

**Workaround for IDE/restricted-environment users**: clone the skill's
scripts and run them manually outside the restricted environment, then
bring the results into a Claude Code session for the fixing phase:

```bash
cd /path/to/your/frontend-repo
python3 /path/to/dynatrace-triage/scripts/eligibility.py errors.csv --first-party-domain <your-domain> --min-users 100 --out queue.json
# then invoke this skill in Claude Code, pointing it at queue.json, for diagnosis/fix/MR
```

This gives restricted-environment users the eligibility-filtering and
registry tooling even when full auto-fix orchestration requires Claude Code.

## Confidence Scoring (Summary)

| Confidence | Source | Fix |
|---|---|---|
| **High** | ≥2 aligned signals (function name, module, error property match) | Restores the correct invariant, focused change, test covers the failure path |
| **Medium** | 1 strong signal + supporting context | Defensive fix with explicit assumptions documented in the MR body |
| **Low** | Ambiguous signals, multiple candidates | Report-only — no auto-fix |

**Auto-fix gate (Mode 3)**: high source + high fix, OR medium source +
medium fix with assumptions. Low confidence on either axis → report-only,
never a guess. Full rubric and fix-hierarchy: [architecture-rules.md](./references/architecture-rules.md).

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

Command pattern: `dynatrace_triage heal [--csv <path> | --source token|browser] --first-party-domain <domain> [--repo <path>] [--min-users 100] [--dry-run]`

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

Post-merge verification is recommended, not optional in spirit: an
`auto-fixed` status is a claim (tests + build passed) until confirmed —
query Dynatrace again ~15-60 minutes after the MRs deploy, and again across
the following 7 days, to confirm affected-user counts actually dropped. See
[auto-heal-workflow.md](./references/auto-heal-workflow.md) Phase 4.
