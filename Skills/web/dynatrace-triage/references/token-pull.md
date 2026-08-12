# Token Pull — Grail DQL Path

Acquires the eligible-error dataset by querying Dynatrace Grail directly with a
platform token, with no browser session involved. This is the **preferred Mode 3
acquisition path** when a token is available; [live-pull.md](./live-pull.md) is
the fallback for when it isn't.

Everything below was verified live against a real tenant — the data object names,
field names and the 403 signatures are observed, not inferred from documentation.

## Contents

- [When to use this path](#when-to-use-this-path)
- [Setup](#setup)
- [Endpoint and auth](#endpoint-and-auth)
- [The data object](#the-data-object)
- [The acquisition query](#the-acquisition-query)
- [Normalize to the canonical row shape](#normalize-to-the-canonical-row-shape)
- [Impact metric caveat — sessions, not users](#impact-metric-caveat--sessions-not-users)
- [Troubleshooting 403s](#troubleshooting-403s)
- [Explicitly out of scope for this path](#explicitly-out-of-scope-for-this-path)

## When to use this path

Whenever `DT_API_TOKEN` is set (or the user points at a token file). It is
faster, deterministic, and paginates without screenshots. Fall back to
[live-pull.md](./live-pull.md) only if no token is available or the token cannot
be granted the Grail RUM read permission.

## Setup

`DT_API_TOKEN` must hold a Dynatrace **platform token** (`dt0s…`) generated from
the target environment.

A platform token only works within the limits of the permissions of the user who
generated it — it is not a standalone service credential. The token owner needs
Grail read on the RUM buckets, granted as an IAM policy statement in
**Account Management → Identity & Access Management → Policies**, scoped to the
target environment:

```
ALLOW storage:user.events:read, storage:user.sessions:read;
```

Policy grants apply to an existing token immediately — no regeneration needed,
because the token evaluates against the owner's current permissions on each call.

Read the token from the environment; never inline it in a script, a query, or a
committed file.

## Endpoint and auth

```
POST https://<tenant>.apps.dynatrace.com/platform/storage/query/v1/query:execute
GET  https://<tenant>.apps.dynatrace.com/platform/storage/query/v1/query:poll?request-token=<t>
```

- Body: `{"query": "<DQL>", "dtClientContext": "<label>"}`
- Header: `Authorization: Bearer <token>` for `dt0s…` platform tokens;
  `Api-Token <token>` for legacy classic tokens. Pick by prefix.
- `:execute` may return `SUCCEEDED` inline, or a `requestToken` to poll. Poll on
  a backoff until `state`/`status` is `SUCCEEDED` or `FAILED`; treat a timeout as
  a blocker, not an empty result.
- Python 3 stdlib only (`urllib.request`) — `requests` is not guaranteed present
  and `pip install` is out of scope.

## The data object

Browser errors live in **`user.events`**. Sibling name guesses do *not* exist and
return `UNKNOWN_DATA_OBJECT` (a DQL syntax error, not a permission error):
`usersessions`, `useractions`, `user.errors`, `user.exceptions`, `dt.rum.*`.
`user.sessions` exists but holds per-session rollups (`error.exception_count`
etc.), not individual errors.

Fields that matter for triage:

| Field | Notes |
|---|---|
| `error.name` | The error string as the Error Inspector shows it |
| `error.display_name` | Usually identical to `error.name` |
| `error.type` | `exception` \| `request` \| `csp` — **filter to `exception`** |
| `error.source` | `console` \| `exception` \| `promise_rejection` — a capture *kind*, never a URL |
| `error.id` | Dynatrace's own stable error id |
| `exception.message`, `exception.stack_trace` | Evidence for Phase 2A |
| `frontend.name` | Scope to the target app |
| `dt.rum.session.id` | The impact metric — see the caveat below |
| `view.url.path`, `page.url.full` | Top-pages evidence |

`error.source` is a common trap: filtering it for `extension://` or a domain
matches nothing, because it only ever holds one of those three capture kinds.
Match third-party and browser-extension origins against `error.name`,
`exception.message` and `exception.stack_trace` instead.

## The acquisition query

The skill's three targeting criteria — **3-day window, 1st-party only, ≥100
affected users** — map onto the query and `eligibility.py` like this: the window
and the error-type/frontend scope are enforced in DQL; the 1st-party filter and
the users threshold are enforced by `eligibility.py` so both acquisition paths
classify identically.

```dql
fetch user.events, from:-3d
| filter frontend.name == "<frontend-id>" and error.type == "exception"
| summarize sessions = countDistinct(dt.rum.session.id), occurrences = count(),
    by:{error.name, error.source}
| filter sessions > 100
| sort sessions desc
| limit 60
```

- `from:-3d` — the 3-day rolling window. **Always 3 days.**
- `error.type == "exception"` — never widen to `request` or `csp` without being
  asked. Leaving it off buries real exceptions under ad/analytics request noise.
- Aggregate server-side with `summarize`. Never pull raw error records and count
  them client-side — that scans orders of magnitude more data for the same answer.
- Keep `limit` small and the window tight; a wide unaggregated `fetch` over
  `user.events` scans hundreds of millions of records.

For per-candidate evidence in Phase 2A, query one error at a time rather than
fetching stacks for the whole queue:

```dql
fetch user.events, from:-3d
| filter frontend.name == "<frontend-id>" and error.type == "exception"
    and error.name == "<error name>"
| fields exception.message, exception.stack_trace, view.url.path, browser.name
| limit 5
```

## Normalize to the canonical row shape

Map each aggregated row to [eligibility.md](./eligibility.md)'s schema, then run
the same filter the browser path uses:

```json
{
  "error_id": "<short SHA-1 prefix of the normalized error name>",
  "error_text": "<error.name, verbatim>",
  "severity": "", "signal": "<error.source>",
  "users": <sessions>, "count": <occurrences>,
  "teams": "", "top_pages": "", "browsers": ""
}
```

`error.name` is the stable identity here — derive `error_id` by hashing it so
repeated runs dedupe against the registry. (Dynatrace's `error.id` varies per
occurrence and is not a grouping key.)

```bash
python3 scripts/eligibility.py <rows.json> --min-users 100 \
  --first-party-domain <domain> --out <workspace>/queue-<run_id>.json
```

## Impact metric caveat — sessions, not users

`user.events` exposes no user- or device-identity field (`dt.rum.user.id`,
`user.id`, `dt.rum.visitor.id`, `dt.rum.device.id` all return zero distinct
values), so the impact metric on this path is **distinct `dt.rum.session.id`**,
not the Error Inspector's "Affected Users".

Observed live: for an identical window and filter, this path reported 150,345
sessions / 153,284 occurrences where the UI reported 15,520 users / 15,336
occurrences — roughly 10× apart. Record identity on the Grail side checks out
(153,295 records carrying 152,193 distinct ids, so nothing is fanning out), but
the UI's metric definition could not be reconciled from the API.

Consequences to carry into any report:
- **Ranking is reliable**; the absolute scale is not directly comparable to the UI.
- `--min-users 100` is therefore a *sessions* threshold on this path. If a run
  needs to match the UI's user counts exactly, say so plainly rather than
  presenting sessions as users — and note that the same threshold is stricter in
  UI terms.
- Label the column "sessions" in every board and report produced from this path.

## Troubleshooting 403s

| Response | Cause | Fix |
|---|---|---|
| `An error occurred during SSO authentication to the Dynatrace environment.` | Token belongs to a different environment, or is expired/revoked. An expired platform token still lists as active. | Regenerate from within the target environment. |
| `OAuth token is missing required scope. Use one of: [<scope>]` | Token is valid; the named permission isn't granted. | Add exactly the named scope to the owner's IAM policy. The message names it — don't guess. |
| `UNKNOWN_DATA_OBJECT` (HTTP 400) | Wrong data-object name — a DQL syntax error, *not* a permission problem. | Use `user.events`; see [The data object](#the-data-object). |

Never widen scope or retry blindly against a 403. Report the exact message and
which of the three causes it matches.

## Explicitly out of scope for this path

- The classic `/api/v1/userSessionQueryLanguage/*` (USQL) endpoints on
  `<tenant>.live.dynatrace.com` — gated behind
  `environment-api:usersessionquerylanguage:read`, which is not a grantable
  permission on Grail-only tenants. Do not build on it.
- Error types other than `exception` (`request`, `csp`) — a separate, explicit run.
- Widening the window past 3 days to "get more data".
