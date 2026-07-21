# dynatrace-triage

A Claude Code skill for triaging and fixing Dynatrace client-side errors on
an Angular (or similar) web frontend — from a single reviewer-grade fix, to a
strategic summary of your worst recurring errors, to a fully automated
batch-heal pipeline that pulls high-impact 1st-party exceptions straight from
Dynatrace, shows you the plan before touching code, fixes what it's
confident about, and opens one MR per fix.

---

## Prerequisites

- [Claude Code](https://claude.ai/code) installed, with filesystem + bash
  access to your frontend repo
- A Dynatrace tenant with your app's browser/RUM monitoring configured
- `git` + a Git hosting CLI (`glab` for GitLab, `gh` for GitHub) for MR/PR
  creation in Mode 3
- For the browser acquisition path: a Chrome session authenticated against
  your Dynatrace tenant (no extra token needed)
- For the token/DQL acquisition path (optional): a Dynatrace API token with
  `storage:query:read` scope, set as `DT_API_TOKEN`

The Mode 3 test gate assumes an Angular-style `pnpm test`/`eslint` setup —
adjust [auto-heal-workflow.md](./references/auto-heal-workflow.md)'s test
commands if your project uses a different stack.

---

## Setup

**1. Copy the skill into your project**

```
your-project/
└── .claude/
    └── skills/
        └── dynatrace-triage/
            ├── SKILL.md
            ├── references/
            └── scripts/
```

**2. Fill in your project's specifics**

Nothing here is Halodoc-specific, but you must supply your own values —
see the "Configure for your project" table at the top of
[SKILL.md](./SKILL.md):

- Your site's domain(s), for the 1st-party filter (`--first-party-domain`)
- Your Dynatrace app/frontend id
- Where your production sourcemaps are stored ([sourcemaps.md](./references/sourcemaps.md))
- A short module map for your own routing ([module-map.md](./references/module-map.md))

**3. (Optional) Set `DT_API_TOKEN`** if you want the token/DQL acquisition
path available. Skip this to use the browser-only path — no credentials
needed at all.

---

## Usage

```
"use this skill to fix <dynatrace-error-id>"
"summarize the highest-risk recurring Dynatrace frontend errors"
"heal ./errors.csv"
"heal --source browser"
"pull the latest browser exceptions from Dynatrace and auto-fix the high-impact ones"
```

Claude picks the mode from your intent:

| Mode | What it does |
|---|---|
| **1 — High-Confidence Fix** | Diagnose and fix one specific Dynatrace error, with a reviewer-grade MR |
| **2 — Strategic Summary** | Rank and group your worst recurring errors into a remediation roadmap |
| **3 — Auto-Heal Batch** | Pull errors live (browser or token) or from a CSV, hard-filter to 1st-party high-impact exceptions, show the pre-fix plan, then fix with no approval prompt — one MR per fix, full attribution |

See [auto-heal-workflow.md](./references/auto-heal-workflow.md) for Mode 3's
full phase-by-phase behavior.
