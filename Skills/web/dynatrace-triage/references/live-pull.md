# Live Pull — Browser Path

Acquires the eligible-error dataset directly from the Dynatrace Error
Inspector Explorer UI via the `claude-in-chrome` tools, using the analyst's
own authenticated browser session — no `DT_API_TOKEN` or new credentials
required. This is one of the three acquisition paths chosen in Phase -1 of
[auto-heal-workflow.md](./auto-heal-workflow.md) (the other two: `token-pull.md`,
manual CSV).

## Contents

- [When to use this path](#when-to-use-this-path)
- [Procedure](#procedure)
- [Explicitly out of scope for this path](#explicitly-out-of-scope-for-this-path)
- [Future v2 note](#future-v2-note)

## When to use this path

- No `DT_API_TOKEN` is configured, or the user prefers not to provision one
  for this run.
- A Chrome session with access to the tenant is available
  (`mcp__claude-in-chrome__*` tools).

## Procedure

### 1. Load the tools

```
ToolSearch: select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__find,mcp__claude-in-chrome__read_network_requests
```

### 2. Navigate to the Explorer

URL template (adjust `Frontend`/tenant per target app):

```
https://<tenant>.apps.dynatrace.com/ui/apps/dynatrace.error.inspector/error-explorer?tf=now-7d%3Bnow&perspective=impact&sort=affected_users%3Adescending&sidebarOpen=true&tab=occurrence&group=occurrences#filtering=Frontend+%3D+<frontend-id>+%22Error+Type%22+%3D+Exception+
```

- `tf=now-7d;now` — the 7-day rolling window (widened from 3 days).
- `sort=affected_users:descending` — biggest impact first.
- `filtering=Frontend = <frontend-id> "Error Type" = Exception` — scope to
  the target app's Exception errors only (never widen to Failed request /
  CSP rule violation without being asked).

**Known quirk**: on a fresh tab, this URL sometimes lands on an app-switcher
page showing only the left nav with an "Open Error Inspector" link — find and
click that link once, then wait ~3-5s for the real Explorer table to render.
Confirm via the page title (`Error Inspector - <tenant> - Dynatrace`) and a
screenshot showing the results table, not just the nav sidebar.

### 3. Extract rows

The accessibility tree does not expose this app's data grid (confirmed: `find`
and `get_page_text` return only the nav/dock, never the table rows) — this is
a custom grid component, not standard HTML/ARIA. Extraction is
**screenshot-based**: take a screenshot, read the visible rows (Error Name,
Affected Users, Occurrences, Last Occurred, Frontends) directly from the
image, scroll and repeat.

**Cost-bounding rule**: the table is sorted by affected users descending —
stop scrolling/extracting once a row's affected-user count drops
meaningfully below `min_users` (default 100); do not paginate through the
entire tail of low-impact errors.

### 4. Normalize to the canonical row shape

For each extracted row, build a canonical JSON object matching
[eligibility.md](./eligibility.md)'s schema:

```json
{
  "error_id": "<stable slug — see note below>",
  "error_text": "<Error Name column, verbatim>",
  "severity": "",
  "signal": "",
  "users": <Affected Users, as printed>,
  "count": <Occurrences, as printed>,
  "teams": "",
  "top_pages": "",
  "browsers": ""
}
```

- The Explorer's visible columns don't include a stable `error.id` the way
  the CSV export does. Derive a stable id by hashing the normalized error
  text (e.g. a short SHA-1 hex prefix) so repeated runs produce the same id
  for the same error and dedupe/re-run logic in the registry still works.
- `severity`/`signal`/`teams`/`top_pages`/`browsers` are populated later, per
  candidate, from the row detail panel (step 5) — leave empty here if not
  yet fetched; they are not needed for the eligibility.py classification
  pass, only for the downstream evidence/diagnosis step.

Write the full list to a JSON file and run:

```bash
python3 scripts/eligibility.py --json <rows.json> --min-users <n> --out <workspace>/queue-<run_id>.json
```

### 5. Per-candidate detail drill-down (evidence for Phase 2A)

For each row that survives `eligibility.py` (1st-party + threshold), click
into it to expand detail — the URL's own params document the available
sections: `expandedSections=instances,pages,details&tab=occurrence`. Look
for: a sample stack trace, top affected pages, browsers/devices breakdown,
and (if present) a session-replay link. Exact click targets/selectors are
UI-specific and may shift with Dynatrace releases — locate them fresh each
run via `find`/screenshot rather than hardcoding coordinates; if a detail
element can't be located, note the gap and proceed with whatever evidence was
gathered (never block the whole run on one row's UI quirk).

## Explicitly out of scope for this path

- Any Dynatrace API/DQL calls — this path never touches `DT_API_TOKEN`.
- Errors outside the applied filter (Failed request, CSP rule violation) —
  do not switch these on to "see more data"; if the user wants a different
  Error Type scope, that's a separate, explicit run.

## Future v2 note

A non-interactive variant (no live browser session, e.g. for a CI trigger)
would need [token-pull.md](./token-pull.md)'s DQL path instead — out of scope
for this round.
