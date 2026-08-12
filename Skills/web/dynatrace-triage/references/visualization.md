# Visualization (Pre-Fix Triage Board + Post-Run Summary)

Auto-heal (Mode 3) never goes straight from eligibility filtering into
fixing. Between Phase 2A (diagnose all, no side effects) and Phase 2B
(execute), and again after Phase 2B finishes, render a readable visual board
via the `Artifact` tool — a single HTML page, redeployed to the same URL for
the "before" → "after" update.

**Before calling `Artifact` for the first time in a run, load the
`artifact-design` skill** (per the tool's own instructions) to calibrate
layout/design effort — this is a data-dense internal ops board, not a
polished marketing page; favor a dense, scannable table over heavy visual
design.

## Pre-fix triage board (after Phase 2A, before Phase 2B)

One row per error that survived `eligibility.py`'s hard 1st-party + threshold
filter, **plus** a visible section listing what was excluded — auditability
matters as much as the queue itself.

### Main table — one row per diagnosed candidate

| Column | Content |
|---|---|
| Error | error text (truncated) + error_id |
| Affected Users | from the pull, sorted desc |
| Top pages | the 2-3 highest-session `view.url.path` values for this error, with counts — where it actually happens. `—` if the pull returned none |
| Root-Cause Hypothesis | one-line `symptom → trigger → root_cause` from Phase 2A's diagnosis |
| Confidence | `source_confidence / fix_confidence` (e.g. `high/high`, `medium/low`) |
| Planned Action | `Auto-Fix` or `Report-Only`, color-coded (green / gray) |

Sort by Affected Users descending — matches the eligibility queue order.

**Top pages is not optional.** It is the strongest routing signal on the
board: an error concentrated on one path is a route-specific fault and names
the module to open, while one spread across many paths and led by `/` is a
bootstrap/app-shell fault where the page list is deliberately uninformative.
Say which of the two a row is, rather than leaving the reader to infer it.

### Excluded section (below the main table, collapsible or visually secondary)

Two small lists, not full tables:
- **Skipped — 3rd-party**: error text + which signal matched (vendor
  pattern / extension scheme / non-first-party domain / opaque cross-origin).
- **Skipped — below threshold**: error text + affected users (so it's clear
  why, e.g. "38 < 100").

### Header summary

Run id, source (live dashboard pull), time window (3 days), total rows seen,
counts per bucket (eligible / skipped-3rd-party / skipped-below-threshold),
and a note: *"Planned actions below are not yet executed — this is a preview."*

## Post-run board (redeploy same Artifact after Phase 2B)

Same row set, columns updated to reflect what actually happened:

| Column | Content |
|---|---|
| Error | unchanged |
| Affected Users | unchanged |
| Top pages | unchanged |
| Outcome | `Fixed` / `Reported` / `Fix Failed → Reported` — color-coded (green / gray / amber) |
| Detail | for Fixed: MR link; for Reported: one-line reason (low confidence, or test-gate failure) |

### Header summary (updated)

Replace the "preview" note with the actual metrics from `registry.py report`:
remediation rate vs the 75% target with an explicit verdict, MR coverage of
auto-fixed (must read 100%), and any blockers (e.g. `glab` missing →
`auto-fixed-mr-pending` rows called out).

## Worked example (one row, pre-fix board)

| Error | Affected Users | Top pages | Root-Cause Hypothesis | Confidence | Planned Action |
|---|---|---|---|---|
| `TypeError: Cannot read properties of undefined (reading 'currentValue')` — `261e721354a6680a` | 178 | `symptom:` ngOnChanges throws on a partial changes object → `trigger:` fast re-render omits an entry → `root_cause:` missing existence guard before dereferencing `currentValue` | high/high | **Auto-Fix** (green) |

Excluded section for the same run:

> **Skipped — 3rd-party**: `Script error.` (1,410 users) — opaque cross-origin;
> `pagead2.googlesyndication.com/…/adsbygoogle.js:221` (260 users) — vendor
> pattern + non-first-party domain.
> **Skipped — below threshold**: `undefined is not an object (evaluating 't.documents[0]')` (38 users) — 38 < 100.

## Rules

- Never omit the excluded/skipped sections — a board that only shows the
  happy path misrepresents what the pipeline actually did with the full
  pulled dataset.
- Keep the same Artifact `file_path`/title across the pre- and post-run
  render so the second `Artifact` call redeploys to the same URL rather than
  creating a second page for one run.
- This Artifact is a human-readable companion to the machine-readable
  registry + markdown run report ([registry-format.md](./registry-format.md))
  — it does not replace them; the registry remains the source of truth for
  the attribution lifecycle and the 75%-target verdict.
