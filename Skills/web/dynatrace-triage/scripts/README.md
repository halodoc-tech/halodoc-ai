# Dynatrace Triage Scripts

## parser.py

Extract a single CSV row by `error.id`:

```bash
python3 parser.py /path/to/errors.csv 0d2c159d985f24ef
```

The script emits the matching row as formatted JSON.

Use the script when:
- the CSV is large
- you want deterministic row extraction
- you want to avoid rewriting ad hoc parsing snippets

## eligibility.py (Mode 3)

Filter a Dynatrace Error Inspector CSV — or a canonical JSON row list from a
live browser/token pull — into an auto-heal work queue:

```bash
python3 eligibility.py /path/to/errors.csv --first-party-domain example.com --min-users 100 --out queue.json
# or, for live-pulled rows (see references/live-pull.md / token-pull.md):
python3 eligibility.py --json /path/to/rows.json --first-party-domain example.com --min-users 100 --out queue.json
```

`--first-party-domain` is **required** — pass your own site's domain(s), repeating the flag for multiple.

Emits eligible errors (confirmed 1st-party AND users >= threshold) sorted by
affected users descending, plus skipped rows with reasons
(`skipped-3rd-party` / `skipped-below-threshold`). 1st-party is a HARD
exclusion checked before the threshold — never a "suspected" soft flag.
Rules: `references/eligibility.md`.

## registry.py (Mode 3)

Attribution registry — full fix lifecycle per error:

```bash
python3 registry.py init      registry.json --run-id heal-2026-07-03-1 --csv errors.csv --base-sha <sha> --repo <path>
python3 registry.py preflight registry.json --run-id heal-2026-07-03-1 --result already-enabled
python3 registry.py update    registry.json --run-id heal-2026-07-03-1 --error-id <eid> --status auto-fixed \
    --branch fix/error-<eid>-<ctx> --branch-point-sha <sha> --mr-url <url> \
    --confidence-source high --confidence-fix high
python3 registry.py finalize  registry.json --run-id heal-2026-07-03-1
python3 registry.py report    registry.json --run-id heal-2026-07-03-1
python3 registry.py verify    registry.json --run-id heal-2026-07-04-1 --fresh-source fresh.csv
```

`--fresh-source` accepts either a CSV export or the canonical JSON row list
(detected by file extension) — `--fresh-csv` is kept as a backward-compatible
alias. The `registry.json` positional path can be omitted on every subcommand
if `$REGISTRY_PATH` is set (recommended in CI, where `$HOME` is often
ephemeral/per-job).

Schema and status lifecycle: `references/registry-format.md`.
