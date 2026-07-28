# Live Pull — Token/DQL Path

Acquires the eligible-error dataset via the Dynatrace Grail Storage Query API
using `DT_API_TOKEN`, mirroring the pattern already used by the
`performance-analysis-and-auto-fix` skill's `dt_trace_analyzer.py` for
backend 5xx/4xx (env var, token-type auto-detection, retry-on-429, polling).
This is one of the three acquisition paths chosen in Phase -1 of
[auto-heal-workflow.md](./auto-heal-workflow.md) (the other two: `live-pull.md`
browser, manual CSV).

**Security**: `DT_API_TOKEN` is sensitive — it grants read access to
production error data, which may include PII in stack traces/URLs. Never
include its value in logs, error messages, stderr output, or MR bodies. If
authentication fails, report "Dynatrace API authentication failed — verify
token scope `storage:query:read`", never echo the token itself.

## Contents

- [Why this needs a discovery step first](#why-this-needs-a-discovery-step-first)
- [Procedure](#procedure)
- [Cost discipline](#4-cost-discipline)
- [Explicitly out of scope for this path](#explicitly-out-of-scope-for-this-path)
- [Relationship to the browser path](#relationship-to-the-browser-path)

## Why this needs a discovery step first

`dt_trace_analyzer.py` only knows the backend `spans` bucket — it has no
query for browser/RUM JavaScript exceptions, and no DQL schema for that data
exists anywhere in this codebase today. **Never guess field/bucket names.**
Confirm the real schema once, cheaply, before building the real query.

## Procedure

### 1. Preconditions

```bash
[ -z "$DT_API_TOKEN" ] && [ -f ~/.zshrc ] && source ~/.zshrc
[ -z "$DT_API_TOKEN" ] && echo "DT_API_TOKEN not set — set it in your shell profile or CI secret" >&2 && exit 1
```

(The `~/.zshrc` source is a convenience for local macOS/zsh shells only — on
Linux/CI, set `DT_API_TOKEN` directly as an env var or CI secret; the
`[ -f ... ]` guard avoids a spurious "no such file" error when it's absent.)

If missing: report the blocker and offer to fall back to the browser path
([live-pull.md](./live-pull.md)) — do not prompt repeatedly.

Required scope: `storage:query:read` (same as the reference bot). Validate
with a cheap query before anything else:

```
fetch events | limit 1 | fields event.kind
```

On 401/403: report "token rejected — regenerate with scope storage:query:read"
and offer the browser-path fallback.

### 2. One-time schema discovery (cheap, bounded)

Run a small, tightly-scoped query to find the event kind(s) that represent
browser JavaScript exceptions for the target app, e.g.:

```
fetch events, from: -1h, scanLimitGBytes: 1
| filter contains(dt.entity.application, "<frontend-id>") OR contains(affected_entity.name, "<frontend-id>")
| summarize count(), by: {event.kind}
| limit 20
```

If the tenant exposes a RUM-specific bucket instead (e.g. `fetch bizevents`,
`fetch usersessions`), the discovery query should try each in turn with the
same tight bounds (`limit`, `scanLimitGBytes`, a short `from` window) until
one returns rows recognizable as JS-exception events (fields resembling error
message/stack, affected user count, page/URL). Record whichever bucket and
field names actually worked — do not proceed past this step on a guess.

**If discovery finds nothing recognizable**: stop, report the blocker
(`dt_schema_undiscovered`) with what was tried, and fall back to the browser
path. Do not iterate indefinitely — this step is capped at a handful of
attempts precisely to avoid excess query cost.

### 3. The real query

Once the bucket/fields are confirmed, build the actual filtered pull —
7-day window, scoped tightly, matching the same targeting as the browser
path:

```
fetch <confirmed-bucket>, from: -7d, scanLimitGBytes: 100
| filter <frontend-field> == "<frontend-id>"
| filter <error-type-field> == "Exception"
| summarize
    users = countDistinctExact(<user-id-field>),
    occurrences = count(),
    last_seen = max(timestamp),
    by: {<error-name-field>}
| sort users desc
| limit 200
```

Map results into the same canonical row shape used by every other path (see
[eligibility.md](./eligibility.md)): `error_id, error_text, severity, signal,
users, count, teams, top_pages, browsers`. Use a stable id (hash of the
normalized error text) exactly as `live-pull.md` does, so re-runs and the
registry's dedupe logic behave identically regardless of acquisition path.

### 4. Cost discipline

- `scanLimitGBytes` capped on every query (discovery: 1, real pull: 100 — same
  cap the reference bot uses for trace queries).
- `limit` on every query — never an unbounded fetch.
- 7-day window only, never widened silently; if zero rows come back, report
  that plainly rather than auto-retrying with a wider window (unlike the
  reference bot's trace-lookup widening, which is a different, per-trace use
  case).
- Single retry on HTTP 429 using `Retry-After`, matching the reference
  client's behavior.

### 5. Per-candidate detail evidence

For each row surviving `eligibility.py`, fetch instance-level detail (sample
stack, top pages, browsers) with the same bucket/fields confirmed in step 2,
scoped to that single `error_id`/error text and a small `limit`.

## Explicitly out of scope for this path

- Reusing the backend `spans` query verbatim — it is the wrong bucket for
  browser exceptions.
- Any browser/Chrome-extension interaction — this path is fully headless.

## Relationship to the browser path

Both paths feed the identical canonical row shape into `eligibility.py`, so
everything downstream (hard 1st-party filter, threshold, Phase 2A/2B,
visualization, registry) is identical regardless of which was chosen.
