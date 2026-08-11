# android-memory-leak-solver

A Claude Code skill that takes a raw Android LeakCanary trace — pasted directly, pulled
from an issue-tracker ticket, or swept in bulk from your tracker's board — all the way
through to a root-cause analysis, an implemented fix, and the full cascade of pull/merge
requests it takes to publish that fix across a multi-module codebase. No manual reference-
chain reading or multi-repo version-bump bookkeeping required.

---

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Some form of issue-tracker access if you want the **Tracker tickets** or **Fetch all**
  input modes (Jira, Linear, GitHub Issues, etc.) — not required for pasting a trace manually
- A git hosting CLI (`gh`, `glab`, or equivalent) authenticated, for the pull/merge requests
- Your org's placeholders filled in — see Setup below

---

## Setup

**1. Copy the skill into your project**

```
your-project/
└── .claude/
    └── skills/
        └── android-memory-leak-solver/
            ├── SKILL.md
            └── references/
                ├── module_catalog.yaml
                ├── worked_example.md
                └── leak_report_template.md
```

**2. Fill in the Configuration placeholders**

`SKILL.md` opens with a **Configuration** section — every organization-specific detail
(first-party package prefixes, issue-tracker project key, git host CLI, branch/version-file
naming for the multi-module bump workflow, your base app module names) is a named
placeholder there. Set them once before your first real run.

**3. (Optional) Populate the bundled reference files**

None of these are required — each has a documented inline fallback — but they make module
resolution and consumer detection exact instead of inferred:

| File | What it's for |
|---|---|
| `references/module_catalog.yaml` | Maps package prefixes → module name → git repo, so the skill doesn't have to guess which repo owns a leaking class |
| `references/worked_example.md` | Shows the shape of a real multi-repo run — how many pull/merge requests, in what order, for one leak |
| `references/leak_report_template.md` | The fixed structure of the analysis document the skill generates before touching any code |

Each file explains, at its own top, why it exists and how to adapt it — start there.

---

## Usage

Just describe what you want, or paste a trace:

```
"Fix this memory leak" + paste a LeakCanary trace

"Analyse this android leak ticket" + issue-tracker URL

"Fetch all android memory leaks and fix them"
```

## What this skill produces

For every trace, classified first as a library leak (third-party/OS code only) or an app
leak (your own code in the chain):

- **Library leaks** — a brief flagged summary only. No fix is attempted.
- **App leaks**, in full:
  1. **Reference chain narrative** — what holds the reference, and why it outlives what it should
  2. **Root cause** — one precise sentence naming the mechanism
  3. **Steps to reproduce**, including whether the leak compounds on repeated navigation
  4. **An implemented fix**, committed and build-verified
  5. **The full pull/merge-request cascade** — the fix itself, a shared version-catalogue
     bump, and a version bump in every downstream consumer module, in the correct merge order

All of the above lands in one `Android_mem_leaks.md` per run (structure fixed by
`references/leak_report_template.md`), followed autonomously by implementation — this skill
never pauses for confirmation once it starts.

---

## What this skill does not cover

| Concern | Where it lives |
|---|---|
| iOS memory leaks | A separate iOS-specific skill |
| Native C++ memory issues | Android Studio Memory Profiler |
| General performance profiling without a specific trace | Out of scope — the skill will ask for a trace or ticket instead of guessing |
| Reviewing/merging the raised pull/merge requests | You — this skill raises them, it doesn't merge them |

---

## Keeping it current

Update `references/module_catalog.yaml` when a module is renamed, merged, split, or
re-owned — treat drift here the same as you'd treat a stale README. If your org later
builds a shared branching workflow, consumer-detection script, or engineering-standards
doc, point the corresponding `{ORG_...}` placeholder at it instead of relying on the
skill's inline fallback.
