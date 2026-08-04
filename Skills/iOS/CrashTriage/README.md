# ios-crash-triage

A Claude Code skill that takes a raw iOS crash — a Firebase Crashlytics
report, an Xcode `.ips` file, a pasted stack trace, or just a symptom
description — all the way through to a root cause analysis, a Swift fix that
follows your project's conventions, and a ticket draft for your issue tracker. No
manual frame-reading or crash-log archaeology required.

---

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Your team's coding conventions, module ownership, and known crash patterns
  documented in `references/team-conventions.md` (see Setup)

---

## Setup

**1. Copy the skill into your project**

Place this folder anywhere Claude Code can reach it and register it in your
`CLAUDE.md` or skills config:

```
your-project/
└── .claude/
    └── skills/
        └── ios-crash-triage/
            ├── SKILL.md
            └── references/
                ├── team-conventions.md
                └── worked-example.md
```

**2. Populate `references/team-conventions.md`**

This is the only file you must fill in. Open it and replace the placeholder
sections with your team's actual conventions:

| Section | What to put there |
|---|---|
| Coding Conventions | Your architecture pattern, naming prefix (if any), logging utility, and SwiftLint limits |
| Module Owners | Who to assign a crash fix to, per feature area |
| Issue Tracker Config | Your tracker (JIRA, Linear, GitHub Issues), project key, and priority definitions |
| Known Recurring Crashes | Crash patterns your team has seen before, so the skill doesn't re-diagnose them from scratch |
| Do Not Rules | Fixes that have caused problems for your team in the past |

The quality of the root-cause analysis and fix suggestions depends directly
on how complete this file is — an empty template still works, but a filled-in
one produces fixes assigned to the right owner with your team's actual
priority bar.

---

## Usage

Just describe the crash in plain English, or paste/upload the crash artifact:

```
"Triage this crash" + paste Firebase Crashlytics report

"Why is the app crashing on the booking screen?" + attach .ips file

"Help me fix this crash" + paste a raw stack trace
```

If no crash artifact is available yet, the skill will ask:
1. Is there a Firebase issue ID or issue title?
2. Which screen / user flow does it happen on?
3. Is it reproducible or random?
4. Did it start after a specific release or PR?

---

## What this skill produces

For every crash, in order:

1. **Root Cause** — the exact condition that triggered the crash, not just the exception type
2. **Crash Class** — one of: nil/force-unwrap, array bounds, dangling pointer, race condition, stack overflow, assertion, main-thread violation, OOM
3. **Suggested Fix** — before/after Swift code
4. **How to Verify** — steps to reproduce and confirm the fix
5. **Ticket Draft** — ready-to-paste ticket content, formatted for JIRA by default (adjust field names for your tracker)

---

## What this skill does not cover

| Concern | Where it lives |
|---|---|
| Your architecture rules (MVVM/VIPER/TCA specifics) | `references/team-conventions.md` |
| dSYM upload automation | Your CI/CD pipeline |
| Crash monitoring / alerting thresholds | Your Firebase Crashlytics / observability setup |
| Ticket creation (actually filing it) | Your issue tracker's CLI/API — this skill only produces the ticket draft |

---

## Keeping it current

The skill is only as good as `references/team-conventions.md`. Update it
whenever:

- A new crash pattern shows up more than once — add it under Known Recurring Crashes
- Module ownership changes
- Your priority definitions or issue tracker fields change
- A fix pattern turns out to cause new problems — add it to Do Not Rules
