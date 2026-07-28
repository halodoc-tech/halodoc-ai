# Registry Format (Lifecycle Fix Attribution)

The attribution registry is the persistent record of the full fix lifecycle:
error → eligibility decision → branch → MR → verified resolution. It is what
proves the OKR metrics (≥75% remediation rate, 100% MR coverage).

## Location

Default for interactive/local use (recommended — no repo pollution):

```text
~/.claude/dynatrace-triage-workspace/<repo-name>/registry.json
```

Run reports are written next to it as `report-<run_id>.md`.

Alternative: `<target_repo>/.dynatrace-heal/registry.json` (add to
`.gitignore`) if the team wants the registry co-located with the repo.

**In non-interactive/CI mode**: the home-relative default is NOT safe — a CI
runner's `$HOME` is often ephemeral or different per job, so attribution
history would silently fail to persist across runs. Set the `REGISTRY_PATH`
env var to a path mounted/persisted across job runs (e.g. a workspace volume
or artifact cache); `scripts/registry.py` reads it as the default when no
explicit registry path is passed on the command line.

## Managed by `scripts/registry.py`

| Command | When |
|---|---|
| `init` | Phase 0, after base SHA is known |
| `preflight` | after the sourcemap preflight decision |
| `update` | every per-error status change (initial classification, fix, MR, downgrade) |
| `finalize` | Phase 3, computes and freezes run metrics |
| `report` | Phase 3, renders + saves the markdown run report |
| `verify` | Phase 4, transitions statuses against a fresh CSV |

## Schema

```json
{
  "runs": [{
    "run_id": "heal-2026-07-03-1",
    "started_at": "…", "finished_at": "…",
    "csv_path": "…", "repo": "…", "base_sha": "…",
    "min_users": 100,
    "preflight": {"sourcemaps": "already-enabled | enabled-in-mr <url> | failed: <why>"},
    "metrics": {
      "total_rows": 17, "eligible": 12, "auto_fixed": 10, "reported": 2,
      "skipped_3rd_party": 3, "skipped_below_threshold": 2,
      "remediation_rate": 0.8333, "target": 0.75, "target_met": true,
      "mr_coverage": 1.0
    }
  }],
  "errors": {
    "<error.id>": {
      "status": "auto-fixed",
      "error_text": "…", "users": 178,
      "branch": "fix/error-<id>-<context>",
      "branch_point_sha": "<sha of origin/master the branch was cut from>",
      "mr_url": "https://gitlab…/-/merge_requests/…",
      "source_confidence": "high", "fix_confidence": "high",
      "duplicate_group": "grp-1 | null",
      "triage_writeup": "… (populated for reported / skipped entries)",
      "runs": ["heal-2026-07-03-1"],
      "updated_at": "…", "verified_at": null
    }
  }
}
```

## Status lifecycle

```text
(csv row) ─► skipped-below-threshold          terminal for the run
          ─► skipped-3rd-party                terminal for the run
          ─► reported                          low confidence / test-gate failure
          ─► auto-fixed ───────────────► resolved-verified      (verify: absent from fresh CSV)
          ─► auto-fixed-mr-pending ─┘└──► regressed-or-unmerged (verify: still present)
```

- `auto-fixed-mr-pending` = fix pushed but `glab` was unavailable; the exact
  `glab mr create` command is recorded in the report as a blocker.
- `verify` only touches entries in `auto-fixed*` statuses.
- Re-runs must dedupe: skip error IDs already `auto-fixed*` with an open MR.

## Metrics definitions

- `eligible = auto_fixed + reported` (skips are out of scope by design)
- `remediation_rate = auto_fixed / eligible` — compared to the **0.75 target**;
  `null` (reported as N/A) when there are no eligible errors — never 0%.
- `mr_coverage = auto_fixed entries with mr_url / auto_fixed` — must be 1.0;
  anything less is rendered as a defect line in the report.

## Run report structure (rendered by `registry.py report`)

1. Header: run id, repo, CSV, base SHA, timestamps, sourcemap preflight result
2. Blockers (e.g. `glab` missing) — only when present
3. Metrics table with the target verdict line
   (`Remediation rate: 10/12 = 83% — TARGET MET ✅`)
4. Auto-Fixed table: id, status, users, confidences, branch, MR
5. Reported Only table: id, users, error, triage notes
6. Skipped table: id, reason, users, notes
7. Duplicate groups
