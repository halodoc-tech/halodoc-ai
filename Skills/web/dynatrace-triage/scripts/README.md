# Dynatrace Triage Scripts

**No dependencies required.** All scripts use Python 3 standard library only
(`argparse`, `csv`, `json`, `pathlib`, `re`, `datetime`) — no `pip install`
needed.

## Error handling conventions

- **Malformed CSV/JSON input**: a clean one-line message on stderr + exit
  code 1 — never a raw traceback. `parser.py` (Mode 1) rejects malformed CSV;
  `eligibility.py` (Mode 3) rejects invalid JSON, and a `rows`/list shape
  that doesn't match the canonical schema.
- **Corrupted `registry.json`**: `registry.py` reports the parse error and
  exits 1 rather than silently starting from an empty registry (which would
  quietly lose prior attribution history).
- **Atomic writes**: `registry.py` writes to a sibling `.tmp` file and
  renames it into place — a crash or interrupt mid-write can never leave
  `registry.json` half-written/corrupted.
- **Mode 3 batch contract**: a script exiting non-zero for one error is
  treated the same as any other pipeline failure — `registry.py update …
  --status reported --note "pipeline-error: <summary>"`, then the batch
  continues with the next error (see `auto-heal-workflow.md`'s Failure
  isolation section). It is never silently skipped without a registry entry.

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

Filter the canonical JSON row list produced by the browser-driven live-pull
(`references/live-pull.md`) into an auto-heal work queue — this is the only
input format Mode 3 accepts:

```bash
python3 eligibility.py /path/to/rows.json --min-users 100 --first-party-domain example.com --out queue.json
```

Emits eligible errors (confirmed 1st-party AND users >= threshold) sorted by
affected users descending, plus skipped rows with reasons
(`skipped-3rd-party` / `skipped-below-threshold`). 1st-party is a HARD
exclusion checked before the threshold — never a "suspected" soft flag.
Rules: `references/eligibility.md`.

## registry.py (Mode 3)

Attribution registry — full fix lifecycle per error:

```bash
python3 registry.py init      registry.json --run-id heal-2026-07-03-1 --source rows.json --base-sha <sha> --repo <path>
python3 registry.py preflight registry.json --run-id heal-2026-07-03-1 --result already-enabled
python3 registry.py update    registry.json --run-id heal-2026-07-03-1 --error-id <eid> --status auto-fixed \
    --branch fix/error-<eid>-<ctx> --branch-point-sha <sha> --mr-url <url> \
    --confidence-source high --confidence-fix high
python3 registry.py finalize  registry.json --run-id heal-2026-07-03-1
python3 registry.py report    registry.json --run-id heal-2026-07-03-1
python3 registry.py verify    registry.json --run-id heal-2026-07-04-1 --fresh-source fresh-rows.json
```

`--fresh-source` is the canonical JSON row list from a fresh live-pull. The
`registry.json` positional path can be omitted on every subcommand if
`$REGISTRY_PATH` is set (recommended in CI, where `$HOME` is often
ephemeral/per-job).

Schema and status lifecycle: `references/registry-format.md`.
