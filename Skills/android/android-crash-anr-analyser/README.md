# android-crash-anr-analyser

A Claude Code skill that takes an Android crash or ANR (picked from your crash-reporting
backend by ID or by rank, or pasted as a raw stack trace or thread dump) and carries it all
the way to a review-ready fix. It finds the frame that is actually at fault, states and
checks a one-sentence root-cause hypothesis, writes the fix with a reproduction test and a
regression test, compiles and unit-tests the module, and raises every pull/merge request
the fix needs across a multi-module codebase, in merge order. It runs headless, so it works
the same from a terminal or a CI job.

Firebase Crashlytics is the running example throughout because its data model is public.
Any backend that can return an issue summary, sample events with full stacks, and impact
counts works the same way.

---

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Access to your crash-reporting backend from the agent (an MCP server, API client, or CLI).
  Not needed if you only paste traces.
- A git hosting CLI (`gh`, `glab`, or equivalent), already authenticated
- `python3` with a YAML/JSON parser, and a Gradle wrapper in each Android repo
- Your organization's placeholders filled in (see Setup)

---

## Setup

**1. Copy the skill into your project**

```
your-project/
└── .claude/
    └── skills/
        └── android-crash-anr-analyser/
            ├── SKILL.md
            └── references/
                ├── crash_doc_template.md
                ├── output_schema.md
                ├── module_catalog.yaml
                └── worked_example.md
```

**2. Fill in the Configuration placeholders**

`SKILL.md` has a **Configuration** section near the top. Every organization-specific value
is a named placeholder there: your first-party package prefixes, crash-backend project and
app registry, git host CLI, default and fix-branch names, the version-tracker branch and
file, the shared version catalogue and the repo that owns it, and your base app modules.
Set them once before your first real run.

**3. (Optional) Populate the reference files**

| File | What it's for |
|---|---|
| `references/module_catalog.yaml` | Maps package prefixes to modules and git repos, so the skill can clone a repo that isn't on disk yet. Ships with fictional entries; replace them. |
| `references/crash_doc_template.md` | The fixed shape of the analysis document and of every pull/merge-request description |
| `references/output_schema.md` | The JSON the skill writes: `sprint_plan.json`, `test_cases.json`, and the final run result CI can parse |
| `references/worked_example.md` | One fictional ANR run from start to finish, to sanity-check the shape of a real run's output |

If your org already has a shared branching script, consumer-detection script, or coding
standards doc, point the matching `{ORG_...}` placeholder at it. Otherwise the skill uses
its built-in fallbacks.

---

## Usage

Interactively:

```
"Fix this crash" + paste a stack trace
"Analyse this ANR" + paste a thread dump
"Look at the top ANR for the shop app"
"Investigate crashlytics issue <id> for SHOP"
```

Headless (CI), via parameters or environment variables:

```
ISSUE_TYPE=CRASH APP=SHOP ISSUE_RANK=1
ISSUE_TYPE=ANR   APP=SHOP ISSUE_ID=<issue id>
ISSUE_TYPE=CRASH MANUAL_ISSUE_FILE=./trace.txt
```

---

## What this skill produces

For each issue, under `{workspace_root}/{OUTPUT_DIR}/{feature-slug}/`:

1. **`CrashAnalysis_{ShortTitle}.md`**: issue summary, the annotated trace (including the
   lock holder for ANRs), repro steps, the confirmed root cause with its input inventory and
   validation, fix approach, edge cases, regression risk with a release verdict,
   verification, and rollback.
2. **`sprint_plan.json`** and **`test_cases.json`**, a machine-readable plan and test spec.
3. **The fix itself**, with a reproduction test that fails on the old code, a regression
   test, a module compile (up to three repair attempts), and a unit-test run whose result
   appears in every PR body.
4. **The pull/merge-request cascade**: the fix PR; for library modules, one PR on the shared
   version catalogue carrying every bump; and one PR per downstream consumer, including
   consumers with no code change, with base apps last. Each PR states the merge order.
5. **`run_result.json`**, also printed as the last block of output. It is the exit contract
   for CI: status, classification, hypothesis and confidence, versions bumped, PR URLs,
   warnings.

Classification covers ten crash classes plus ANR sub-types (I/O, lock contention, Binder,
heavy CPU), and every issue is tagged by origin: your code, a third-party SDK, or the OS.
SDK and OS issues get full analysis but only get a code change when there is a real
first-party fix site.

---

## What this skill does not cover

| Concern | Where it lives |
|---|---|
| iOS, web, React Native, backend crashes | Platform-specific tooling |
| Non-fatal exceptions in top-issues mode | Paste the trace instead (manual mode) |
| Jank or slow frames without an ANR | A profiler |
| Instrumented / on-device test runs | Your device-test pipeline |
| Reviewing or merging the pull/merge requests | You. The skill pushes and opens PRs and never merges them. |

---

## Keeping it current

- Update `references/module_catalog.yaml` whenever a module is added, renamed, split, or
  moved to another repo. A stale catalog clones the wrong repo.
- Keep `{VERSION_TRACKER_FILE}` complete. Every publishable module needs a row, or the
  skill stops rather than guess a version.
- If your build moves from one version-catalogue format to another (e.g. a `Versions.kt`
  object to `libs.versions.toml`), update `{SHARED_VERSION_CATALOGUE}` and check the
  consumer-detection passes in Step 4h still match how your build files reference
  internal libraries.
- If you change crash backends, only Steps 2–3 change. The rest of the method doesn't
  depend on the vendor.
