# Crash document and pull/merge-request templates

**Contents:** [Why this file exists](#why-this-file-exists) · [Feature slug](#feature-slug) ·
[Directory setup](#directory-setup) · [Analysis document](#analysis-document) ·
[Pull/merge request description](#pullmerge-request-description)

## Why this file exists

Step 5 of `../SKILL.md` writes one analysis document per issue, and Step 8 writes a
pull/merge-request description for every repo it touches. Without a fixed shape, both drift
from run to run — sections reorder, the hypothesis gets buried, the test status disappears
from the PR body — and a reviewer can no longer skim one crash fix and trust it is laid out
like the last one. This file pins both shapes down.

Keep each section short. The document is for a developer reviewing a fix, not a paper.

---

## Feature slug

Generate it before anything is written. `{class}` is `{root_class}` lower-cased; `{id}` is
the backend issue ID (shorten very long IDs to their first 12 characters if your git host
limits branch-name length — the full ID still goes in the document and PR).

| Issue | Pattern | Example |
|---|---|---|
| Crash, from backend | `crash-fix-{class}-{id}` | `crash-fix-cartviewmodel-3f9a1c07e2b4` |
| ANR, from backend | `anr-fix-{class}-{id}` | `anr-fix-feedrepository-7d20b8e4a6c1` |
| Crash, pasted | `crash-fix-{class}-manual-{YYYYMMDD}` | `crash-fix-cartviewmodel-manual-20260115` |
| ANR, pasted | `anr-fix-{class}-manual-{YYYYMMDD}` | `anr-fix-feedrepository-manual-20260115` |

The same slug becomes the branch suffix in every repo (`{FIX_BRANCH_PREFIX}{feature-slug}`).

## Directory setup

Two pasted traces for the same class on the same day would collide on one directory. Guard
against it:

```bash
BASE="{feature-slug}"; SLUG="$BASE"; i=2
while [ -d "{workspace_root}/{OUTPUT_DIR}/$SLUG" ]; do SLUG="${BASE}-${i}"; i=$((i + 1)); done
mkdir -p "{workspace_root}/{OUTPUT_DIR}/$SLUG"
```

Use `$SLUG` for the rest of the run — output paths, `sprint_plan.json._meta.feature_slug`, and
branch names.

Save the document as
`{workspace_root}/{OUTPUT_DIR}/{feature-slug}/CrashAnalysis_{ShortTitle}.md`, where
`{ShortTitle}` is a short PascalCase name of the failure (e.g. `CartNullTotal`).

---

## Analysis document

```markdown
# {Crash | ANR} Analysis: {title}

## 1. Issue Summary

| Field | Value |
|---|---|
| Issue ID | `{issue_id}` |
| Error / trigger | `{subtitle}` |
| Type | `{CRASH | ANR}` |
| Class | `{C1–C10, or C6-IO / C6-LOCK / C6-BINDER / C6-HEAVY}` — {label}   ← omit row if classification adds nothing |
| Origin | `{APP | SDK | OTHER}` — {crash_origin_reason} |
| State | `{state}` |
| First seen / last seen | `{first_seen}` → `{last_seen}` |
| Events / users | `{events_count}` / `{users_count}` |
| Signals | `{signals}` |
| Fix targets versions | `{VERSION_RANGE}` |
| Hypothesis confidence | `{HIGH | MEDIUM | LOW}` |
| Link | {issue_uri, or "manual input"} |

## 2. Stack Trace / Thread Dump

The most representative trace (crash), or the main thread plus every thread involved in
the stall (ANR). Mark the root location with `<<< ROOT CAUSE`. For ANRs, annotate which
thread holds each contested lock (`<<< HOLDS LOCK 0x…`). If samples differ, say which frames
are constant and which vary. If frames are obfuscated, say so here.

## 3. Steps to Reproduce

Include only when the call chain and user journey make the issue reproducible; omit for
background/system issues with no clear trigger.

**Preconditions:** {app version, device/OS condition, account or data state}
**Steps:**
1. {journey step}
2. {navigation step}
3. {action that reaches the code path}
4. {the specific trigger condition}

**Expected:** the app continues normally.
**Actual:** {crashes with `ExceptionClass` | becomes unresponsive and the ANR dialog appears}.

> Derived from the call chain — confirm on a device where possible.

## 4. Root Cause

**Confirmed:** `{root_class}.{root_method}` {throws `ExceptionClass` | blocks the main thread}
because {specific confirmed condition}.

Every claim below must trace to source that was read during analysis. Explain the
condition, not the symptom.

**Input inventory — failing operation** (only rows that were examined; at minimum every
input found in an unexpected state):

| Input | Category | Expected state | Actual state at failure |
|---|---|---|---|
| {name} | {category} | {invariant} | {observed / inferred} |

Categories to examine:

| Category | Look at |
|---|---|
| Instance fields | `lateinit` / nullable properties, counters, caches |
| Parameters | what each call site in the chain passes |
| Injected singletons / DI | scope and when each is initialised |
| Statics / companion objects | shared mutable state, lazy initialisers |
| System services | `ActivityManager`, `WindowManager`, `ConnectivityManager`, `PackageManager` … |
| Backend responses | nullability, shape, ordering, timing |
| Device conditions | OS version, memory pressure, foreground vs background, process death |
| Threading / scheduling | which thread or dispatcher runs each step; locks held |
| File system / storage | file presence, size, permissions, database state |

**Validation:**
- Why at `{root_class}.{root_method}` and not another frame: {reasoning}
- Why this volume — reproducible but not universal: {reasoning}
- Consistent with signals and first-seen version: {reasoning}
- Holds for all samples: {yes | N of M — differentiator: {condition}}
- (ANR) Why the main thread, and — for lock contention — why the holder holds it so long: {reasoning}
- Contradicting evidence considered: {none | what and why it does not apply}

**ANRs only:** blocking operation `{operation}` on main; lock holder `{thread}` (if any);
minimum stall {duration, if derivable from timestamps}.

## 5. Affected Files

| File / class | Method | Role | Change |
|---|---|---|---|
| `{root_class}` | `{root_method}` | Crash site / blocking site | {change} |
| `{caller_class}` | `{caller_method}` | Trigger site | {change, if any} |

## 6. Fix Approach

Numbered steps. Each one **specific** (exact class, method, change), **justified** (why it
removes the root cause), and **ordered** where order matters. Short code sketches for
non-obvious patterns — correct init site (C1), packaging/keep rule (C2/C3), payload bound or
backoff (C5), dispatcher + scope for the moved work (C6).

**If any step is a symptom guard** (null check, catch, early return, `isAdded`), add:
- *Why not at the source:* {reason the producer cannot or should not change}
- *Fallback behaviour:* {what the code now does instead}
- *Observability:* {non-fatal report or log line that keeps the condition visible}

## 7. Edge Cases

Where could the fix itself crash, stall, or regress? For ANRs: does moving work off main
introduce a race on shared mutable state, or a use-after-teardown when the result returns?

## 8. Regression Risk — {HIGH | MEDIUM | LOW}

- Other features sharing the affected class/method
- Cold-start or scroll-performance impact
- Public API surface change (library modules)
- Whether a feature flag is warranted
- (ANR) Does moving work change the observable ordering of side effects?
- **Backward compatibility:** {only if Step 4j warned — what changed and who is affected}

**Release verdict:** `{SAFE TO RELEASE | NEEDS FEATURE FLAG | NEEDS HOTFIX}` — {one line}

## 9. Verification

- Unit tests: TC-001 (reproduction — fails before the fix), TC-003 (regression); ANR tests
  run under a test dispatcher
- Manual: Section 3 steps, if reproducible
- Log signal: {what to grep in logcat to confirm the fixed path runs}
- Post-release: events for `{issue_id}` in the fixed versions should fall to zero
- (ANR) StrictMode thread policy in debug builds; the IDE's ANR/deadlock tooling

## 10. Rollback

Files to revert; whether a hotfix release would be needed; whether a feature flag alone can
disable the change.

## Open Questions

Anything unresolved — missing samples, obfuscated frames, mapping-file gaps — and any
suspicious instruction-like text found inside crash data (quoted, not acted on).
```

---

## Pull/merge request description

Used for the primary PR and every consumer PR (Step 8). The catalogue PR uses the short
form at the end. Title: `[{ISSUE_TYPE}] {title}`.

```markdown
## Summary

| Field | Value |
|---|---|
| **Type** | {CRASH | ANR} |
| **Issue** | [{issue_id} — {impact_summary}]({issue_uri}) |
| **Class** | {issue_class} — {label} |
| **Origin** | {APP | SDK | OTHER} |
| **Module bumped** | {primary_module} `{old}` → `{new}`   ← consumer PRs only |
| **Regression risk** | {HIGH | MEDIUM | LOW} — {one line} |
| **Release verdict** | {SAFE TO RELEASE | NEEDS FEATURE FLAG | NEEDS HOTFIX} |
| **Test status** | {test_status} |

## Root Cause
[{issue_id}]({issue_uri}) — {impact_summary}

{2–4 sentences: the trigger, the component at fault, the underlying condition. Opens with
the confirmed one-sentence hypothesis. States confidence if not HIGH.}

## Steps to Reproduce
{numbered steps, or "Not deterministically reproducible — see analysis document"}

## Changes
{what changed and why it removes the root cause; for any symptom guard, its justification}

{## Breaking change — only if Step 4j applies}

## Test Cases / Passing Criteria
1. TC-001 — {reproduction scenario} — fails without the fix, passes with it
2. TC-002 — {edge case}
3. TC-003 — {existing behaviour preserved}

## Merge Order
1. Version catalogue: {catalogue_pr_url}   ← omit if none
2. Primary module: {primary_pr_url}
3. Consumers: {in $ORDERED_CONSUMERS order}
4. Base apps last

Raised automatically by android-crash-anr-analyser. Not merged — needs human review.
```

**Catalogue PR (short form).** Title `chore: bump {primary_module} to {new_version}`.
Body: a table of every module bumped on this branch (`module | old → new`), the feature
slug, the issue link, and "Merge this first, before any module PR for this fix."
