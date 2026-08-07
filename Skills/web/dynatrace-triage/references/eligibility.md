# Eligibility (Auto-Heal Targeting)

## Contents
- [Scope assumptions](#scope-assumptions)
- [1st-party filter — HARD exclusion, not a soft flag](#1st-party-filter--hard-exclusion-not-a-soft-flag)
- [Users threshold](#users-threshold)
- [Canonical row schema](#canonical-row-schema)
- [Status taxonomy](#status-taxonomy)
- [Duplicates / shared root cause](#duplicates--shared-root-cause)
- [Ordering](#ordering)

Rules that scope Mode 3 (auto-heal) to 1st-party EXCEPTION errors impacting
≥100 users within a rolling 3-day window.

## Scope assumptions

Rows always come from the single acquisition path — the browser-driven live
pull of the Dynatrace Error Inspector Explorer, see
[live-pull.md](./live-pull.md). That pull must already be scoped to:

- Frontend = your target production app (e.g. `<your-app-id>` as named in Dynatrace)
- Error Type = Exception
- Time frame = last 3 days (rolling)

`eligibility.py` trusts the source for error type and time window (neither is
carried per-row), and enforces locally what it can:

- **1st-party** — HARD exclusion, checked first (below)
- **users threshold** — enforced second

State this trust boundary in the run report.

## 1st-party filter — HARD exclusion, not a soft flag

Live data has shown 3rd-party noise (ad/analytics scripts, browser
extensions, opaque cross-origin errors) regularly outranking real app errors
by affected-user count. **Any row that fails the 1st-party check is dropped
from the queue immediately, before the users threshold is even checked** —
never a "suspected, confirm later" status. Detection runs in two stages.

### Stage 1 — extraction-time heuristics (hard exclusion, in `eligibility.py`)

Status `skipped-3rd-party` when the error text contains:

- vendor globals/scripts: `gtag`, `gtm`, `googletagmanager`, `fbq`,
  `clevertap`, `moengage`, `appier`, `zE`/`zendesk`, `Sentry`, `dtrum`,
  `newrelic`/`NREUM`, `hotjar`, `mixpanel`, `amplitude`, `googlesyndication`,
  `doubleclick`, `adsbygoogle`
- extension schemes: `chrome-extension://`, `moz-extension://`,
  `safari-web-extension://`, `safari-extension://`, `ms-browser-extension://`
- opaque cross-origin marker: error text is exactly `Script error.`
- **a leading hostname that isn't first-party**: many error names ARE a
  script location (e.g. `pagead2.googlesyndication.com/pagead/js/adsbygoogle.js:221:179`
  vs. `www.<your-domain>/resources/chunk-VOJCN56V.js:3:1861`) — `eligibility.py`
  extracts the leading hostname and hard-excludes any row whose hostname
  doesn't match `--first-party-domain` (**required, no default** — pass your
  own site's domain; matched by exact value or subdomain suffix).

Excluded rows are removed from the fix queue but **still listed on the
pre-fix triage board** ([visualization.md](./visualization.md)) with the
matched signal, so a human can audit or rescue a false positive — they are
never silently dropped from view, only from the queue.

### Stage 2 — evidence stage (authoritative, per-error, Phase 2A)

After fetching stack detail / symbolication, classify frames:

- **1st-party**: frames from the project's own bundles
  (e.g. `<your-domain>/resources/*.js`, or the target project's bundle origin)
- **3rd-party**: extension URLs, non-project CDNs, inline vendor tags,
  anonymous eval frames from injected scripts

Rule: **eligible only if the topmost app-actionable frame is 1st-party.**

- Vendor-topped stack with 1st-party frames below the vendor entry point →
  still eligible; note the vendor frame in the diagnosis.
- Pure vendor/extension stack → final status `skipped-3rd-party` with the
  evidence recorded (same status as stage 1 — this is a second, stricter gate
  on rows that already passed stage 1, not a separate "suspected" tier).

## Users threshold

- Canonical field: `users` (the JSON row key from the live pull). Values may
  be quoted with thousands separators (`"4,120"`), stray spaces, or
  non-breaking spaces.
- Rule: strip every non-digit character, parse int.
- Fail-closed: unparseable → `0` → `skipped-below-threshold`, with a parse
  warning recorded on the entry (never guess a number).
- Eligible iff `users >= min_users` (default 100, `--min-users` to override).

## Canonical row schema

`eligibility.py` classifies a normalized row with keys `error_id, error_text,
severity, signal, users, count, teams, top_pages, browsers`. The live-pull
must emit a JSON list (or `{"rows": [...]}`) of objects with exactly these
keys — see [live-pull.md](./live-pull.md) for how it maps the Explorer's raw
row data into this shape.

## Status taxonomy

| Status | Meaning |
|---|---|
| `eligible` | in the fix queue |
| `skipped-below-threshold` | users < threshold (incl. fail-closed parse) |
| `skipped-3rd-party` | hard-excluded — extraction-time heuristic (stage 1) or evidence-stage stack check (stage 2) |

## Duplicates / shared root cause

Group errors by normalized error text + property name + overlapping top pages.

Policy:

- **One MR per `error.id`** — keeps the 100%-MR metric honest and each fix
  independently revertable.
- Sibling error IDs are cross-referenced in each MR's
  "Related Areas To Audit" section.
- The registry records a shared `duplicate_group` id.
- If two error IDs are fixed by the exact same change: fix the first normally;
  the second MR is cut from a fresh master branch with the same change
  cherry-picked, and its body notes the duplication.

## Ordering

Process the eligible queue sorted by affected users descending — biggest
impact first, which also front-loads progress toward the 75% remediation
target.
