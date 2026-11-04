# android-crash-anr-analyser

A Claude Code skill that takes an Android crash or ANR (picked from your crash-reporting
backend by ID or by rank, or pasted as a raw stack trace or thread dump) and carries it all
the way to a review-ready fix. It finds the frame that is actually at fault, states and
checks a one-sentence root-cause hypothesis, writes the fix with a reproduction test and a
regression test, compiles and unit-tests the module, and raises every pull/merge request
the fix needs across a multi-module codebase, in merge order. It runs headless, so it works
the same from a terminal or a CI job. If you only want the diagnosis, it stops after the
analysis and touches no branch (`ACTION=ANALYSE`).

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
            ├── references/
            │   ├── issue_intake.md
            │   ├── classification.md
            │   ├── consumer_detection.md
            │   ├── version_cascade.md
            │   ├── crash_doc_template.md
            │   ├── output_schema.md
            │   ├── module_catalog.yaml
            │   └── worked_example.md
            └── evals/
                └── evals.json
```

**2. Fill in the Configuration placeholders**

`SKILL.md` has a **Configuration** section near the top. Every organization-specific value
is a named placeholder there: your first-party package prefixes, crash-backend project and
app registry, git host CLI, default and fix-branch names, the version-tracker branch and
file, the shared version catalogue and the repo that owns it, and your base app modules.
Set them once before your first real run.

The version-tracker file must be a Markdown table with the header
`| module | version | updated_by |` and one row per publishable module, with versions in
`MAJOR.MINOR.PATCH` form (an optional `-suffix` is allowed). `references/worked_example.md`
has a sample.

**3. (Optional) Populate the reference files**

| File | What it's for |
|---|---|
| `references/issue_intake.md` | Workspace resolution and the crash-backend calls for Steps 1–3. Edit this if you use a backend other than Crashlytics. |
| `references/classification.md` | Crash classes C1–C10, ANR sub-types, and origin signals |
| `references/consumer_detection.md` | How the skill finds every repo that depends on a library module |
| `references/version_cascade.md` | Branch, version-bump and PR mechanics, what a re-run reuses, and how to recover from a partial run |
| `references/module_catalog.yaml` | Maps package prefixes to modules and git repos, so the skill can clone a repo that isn't on disk yet. Ships with fictional entries; replace them. |
| `references/crash_doc_template.md` | The fixed shape of the analysis document and of every pull/merge-request description |
| `references/output_schema.md` | The JSON the skill writes: `sprint_plan.json`, `test_cases.json`, and the final run result CI can parse |
| `references/worked_example.md` | One fictional ANR run from start to finish, a re-run of the same issue, and a tracker-file sample |
| `evals/evals.json` | Behaviour checks: pasted traces, obfuscated frames, ANR lock holders, the FATAL shape, `ACTION=ANALYSE`, idempotent re-runs, unverified reproductions |

If your org already has a shared branching script, consumer-detection script, or coding
standards doc, point the matching `{ORG_...}` placeholder at it. Otherwise the skill uses
its built-in fallbacks.

---

## Usage

Interactively, in plain language. A pasted trace becomes the input, an app name from your
app registry becomes `APP`, and "ANR" or "not responding" sets the issue type:

```
"Fix this crash" + paste a stack trace          → pasted input, ACTION=FIX
"Analyse this ANR" + paste a thread dump         → pasted input, ANR, ACTION=ANALYSE
"Look at the top ANR for the shop app"          → APP=SHOP, ANR, rank 1, ACTION=ANALYSE
"Investigate crashlytics issue <id> for SHOP"   → APP=SHOP, ISSUE_ID=<id>, ACTION=ANALYSE
```

Headless (CI), via parameters or environment variables. With `CI` set, or a message made only
of `KEY=VALUE` pairs, the default is `ACTION=FIX`:

```
ISSUE_TYPE=CRASH APP=SHOP ISSUE_RANK=1
ISSUE_TYPE=ANR   APP=SHOP ISSUE_ID=<issue id>
ISSUE_TYPE=CRASH MANUAL_ISSUE_FILE=./trace.txt
ISSUE_TYPE=CRASH APP=SHOP ACTION=ANALYSE        # diagnosis only, no branches or PRs
```

**How `ACTION` is chosen:** an explicit `ACTION=` always wins. Otherwise a headless run
(`CI` set, or only `KEY=VALUE` pairs) is `FIX`; a message that says "fix", "patch", or
"raise/open a PR/MR" is `FIX`; anything else ("analyse", "investigate", "look at") is
`ANALYSE`. `ANALYSE` writes the analysis files and stops. It never switches, creates, or
pushes a branch, and never opens a PR.

**Re-running is safe.** The same issue always maps to the same feature slug, and so to the
same branch names. A second run resumes those branches, reuses versions already bumped for
the fix, and reuses open PRs, so it never burns a second version or opens a duplicate PR.
Every commit the skill makes ends with an `Issue: <id>` trailer, which is how it tells its own
branches from anyone else's.

---

## What this skill produces

For each issue, under `{workspace_root}/{OUTPUT_DIR}/{feature-slug}/`:

1. **`CrashAnalysis_{ShortTitle}.md`**: issue summary, the annotated trace (including the
   lock holder for ANRs), repro steps, the confirmed root cause with its input inventory and
   validation, fix approach, edge cases, regression risk with a release verdict,
   verification, and rollback.
2. **`sprint_plan.json`** and **`test_cases.json`**, a machine-readable plan and test spec.
3. **The fix itself** (`ACTION=FIX`). The reproduction test is written and run against the
   old code first, and it must fail there; whether it did is recorded as
   `reproduction_verified`. Then the fix, a regression test, a module compile (up to three
   repair attempts), and a unit-test run whose result appears in every PR body.
4. **The pull/merge-request cascade**: the fix PR; for library modules, one PR on the shared
   version catalogue carrying every bump; and one PR per downstream consumer, including
   consumers with no code change, with base apps last. Each PR states the merge order.
5. **`run_result.json`**, also printed as the last block of output. It is the exit contract
   for CI: status, action, classification, hypothesis and confidence, reproduction check,
   versions bumped (and whether each was reused), PR URLs, warnings.

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
- If a run ends with a `tracker ahead: <module> <version> has no PR` warning, re-run it with
  the same inputs. It picks up the reserved version instead of bumping again
  (`references/version_cascade.md`, section 9).
- Run the cases in `evals/evals.json` after changing `SKILL.md` or a reference file.
- If your build moves from one version-catalogue format to another (e.g. a `Versions.kt`
  object to `libs.versions.toml`), update `{SHARED_VERSION_CATALOGUE}` and check the
  consumer-detection passes in `references/consumer_detection.md` still match how your
  build files reference internal libraries.
- If you change crash backends, only `references/issue_intake.md` (Steps 2–3) changes. The
  rest of the method doesn't depend on the vendor.
