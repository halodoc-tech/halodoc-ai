# Android_mem_leaks.md template

**Contents:** [Why this file exists](#why-this-file-exists) ·
[Brief usage example](#brief-usage-example) · [Template](#template)

## Why this file exists

Step 6 of `../SKILL.md` generates one `Android_mem_leaks.md` per run, covering every leak
found — app leaks and library leaks alike. Without a fixed template, that document's shape
would drift run to run (different section orders, inconsistent severity labels, sometimes
a raw trace pasted in full, sometimes not), making it harder for a developer to skim one
leak's summary and trust it's structured the same way as the last one they reviewed. This
file pins that structure down once, so Step 6 has a single, exact shape to fill in rather
than reinventing the layout each time.

**Use this exact structure.** Keep each section short — the document is a reference for a
developer, not a research paper.

---

## Brief usage example

For a run analysing two tickets — one app leak, one library leak — Step 6 fills the
template below into something like:

```
## Summary
| # | Ticket | Leaked Object | Type | Severity |
|---|--------|---------------|------|----------|
| 1 | ANDROID-1042 | `CheckoutActivity` | App leak | High |
| 2 | ANDROID-1055 | `OkHttp internal` | Library leak | Info |

## Leak 1 — ANDROID-1042: CheckoutActivity
**Leaked object:** `CheckoutActivity`
**Trigger:** Leak fires after backing out of checkout and re-entering it 3+ times.
...

## Library Leak — ANDROID-1055: OkHttp connection pool retains a closed response body
> ⚠️ Library leak — this leak originates entirely within `okhttp3`. No first-party code
> is the cause. Consider upgrading the library or applying the known workaround if one
> exists.
...
```

The full template below is what Step 6 actually populates — the snippet above is just
illustrating how the placeholders get filled in.

---

## Template

```markdown
<!--
  document_type: Android Memory Leak Analysis
  skill: android-memory-leak-solver
  next_step: This skill implements all fixes and raises pull/merge requests autonomously (Steps 8–9)
-->

# Android Memory Leak Analysis

**Document type:** Memory Leak Analysis
**Date:** {today's date, e.g. 16 April 2026}
**Author:** {reporter name from first ticket, or "Team" for manual traces}
**Tickets:** {comma-separated issue-tracker IDs, or "Manual input" for pasted traces}
**Total leaks analysed:** {N app leaks + M library leaks}
**Status:** Ready for implementation — fixes + pull/merge requests raised in Steps 8–9

---

## Summary

| # | Ticket | Leaked Object | Type | Severity |
|---|--------|---------------|------|----------|
| 1 | {TICKET-ID} | `ActivityName` | App leak | High |
| 2 | {TICKET-ID} | `FragmentName` | App leak | Medium |
| 3 | {TICKET-ID} | `LeakCanary internal` | Library leak | Info |

Severity guide: **High** = Activity/Context leak that compounds; **Medium** = View/Fragment
leak; **Low** = one-time non-compounding; **Info** = library leak (not actionable).

---

{For each APP LEAK, one section:}

## Leak N — {Ticket ID}: {Short name of leaked object}

**Leaked object:** `{ClassName}`
**Trigger:** {One-line user journey description}

### Reference Chain
```
{GC Root} → {Class A}.{field} → {Class B}.{field} → ... → {Leaked Object}
```

### Root Cause
{One paragraph, max 4 sentences}

### Steps to Reproduce
{Steps from 5d — keep to under 6 lines}

### Fix Approach
- {bullet 1}
- {bullet 2}
- {bullet 3}

### Raw LeakCanary Trace
<details>
<summary>Expand trace</summary>

```
{full raw trace}
```
</details>

---

{For each LIBRARY LEAK, a brief entry:}

## Library Leak — {Ticket ID}: {Short description}

> ⚠️ **Library leak** — This leak originates entirely within `{library package}`.
> No first-party code is the cause. Consider upgrading the library or applying the
> known workaround if one exists.

**Library:** `{library name and version if known}`
**Leaked object:** `{ClassName}`
**Recommended action:** {upgrade / workaround / ignore — one sentence}

---

## Next Steps

All app leaks above are ready for implementation. This skill implements the fixes and raises
the pull/merge requests itself (Steps 8–9) autonomously, one leak at a time, starting with Leak 1.
```
