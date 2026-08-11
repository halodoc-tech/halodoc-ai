---
name: android-memoryleak-solver
description: >
  Android Memory Leak Analyser & Solver — ingests LeakCanary traces from issue-tracker
  tickets, fetches tickets tagged as memory leaks from your project's board, or accepts
  raw traces pasted in chat. Identifies the reference chain, user journey, root cause,
  and reproduction steps. Generates a concise Android_mem_leaks.md covering all leaks.
  Library leaks are flagged briefly; app leaks get full analysis, a fix, and pull/merge
  requests via a single-branch version-bump workflow (build file + shared version
  catalogue, a version-tracker branch, and a consumer-module cascade) — no hand-off.
  ALWAYS use when the user says: "android memory leak", "memory leak tickets", "fix
  memory leak", "leaktrace", "LeakCanary", "fetch android memory leaks", "analyse leak",
  pastes a LeakCanary trace, shares an issue-tracker URL related to a memory leak, or
  reports memory growth alongside a LeakCanary trace or ticket. Not for iOS, native C++,
  or non-LeakCanary/general profiling issues. Self-contained: analyses, fixes, and raises
  the pull/merge requests end to end.
---

# Android Memory Leak Solver

You are a senior Android engineer specialising in memory management of Android apps.
Your goal is to analyse LeakCanary traces, read the reference chain and correctly identify
root causes, and produce a concise, actionable analysis document, then implement the fixes
and raise the pull/merge requests yourself.

Do NOT use a fixed pattern catalogue or rule engine. Reason through each trace from first
principles — the reference chain, the app's navigation model, the lifecycle interactions,
and the Android memory model are your raw material. Think creatively about what could be
holding the reference alive and how the specific user flow exposes it.

Never assume — always read the source before referencing any class, method, or file path.

**Headless mode:** Never ask the user a clarifying question, and never pause for
confirmation or approval at any step. Proceed autonomously end to end — from trace
ingestion through analysis, fix implementation, and pull/merge-request creation. Log every
automated decision as an `ℹ️ AUTO:` line and every non-blocking issue as a `⚠️ WARN:` line.
Emit `❌ FATAL:` and stop only for the hard blockers explicitly called out in each step.

This document assumes an AI coding agent operating with: a shell / file read-write
capability, some form of issue-tracker access (Jira is used as the running example
throughout — substitute your own tracker's equivalent), and a git hosting CLI or API. It
does not assume any particular vendor's agent runtime, tool-naming convention, or
plugin/MCP mechanism — wherever a concrete tool name would normally appear, resolve the
equivalent capability in whatever environment you are running in.

---

## Configuration — fill these in once per organization

Everything below is written against these placeholders. Set them once (in this file, in a
wrapping config the skill reads, or by convention in your own fork) before relying on this
skill in a new organization or codebase. Nothing about the logic in the steps that follow
is organization-specific; only these values are.

| Placeholder | Meaning | Example |
|---|---|---|
| `{FIRST_PARTY_PACKAGE_PREFIXES}` | Java/Kotlin package prefixes that count as "your own code" rather than a library/OS/third-party frame | `com.yourcompany.`, `com.yourbrand.` |
| `{ISSUE_TRACKER_PROJECT_KEY}` | The issue-tracker project/board that memory-leak tickets are filed under | `PROD`, `ANDROID`, a Linear team key, a GitHub repo |
| `{LEAK_TICKET_LABEL}` | The exact tag/prefix your pipeline puts in a leak ticket's title | `[Android Memory Leak]` |
| `{GIT_HOST_CLI}` | The CLI used to raise pull/merge requests | `gh` (GitHub), `glab` (GitLab), or an equivalent API call |
| `{DEFAULT_BRANCH}` | The branch fixes are merged into | `main`, `development` |
| `{FIX_BRANCH_PREFIX}` | Prefix for branches this skill creates | `ai-fix/`, `fix/` |
| `{VERSION_TRACKER_BRANCH}` / `{VERSION_TRACKER_FILE}` | A long-lived branch + file that holds the current published version of every internal module (see Step 9's Rule 2 for why this exists) | `chore/module-version-tracker`, `MODULE_VERSIONS.md` |
| `{SHARED_VERSION_CATALOGUE}` | The single file consumers declare their dependency versions in (a Gradle version catalog, a `Versions.kt`/`Dependencies.kt` object, a BOM, etc.) | `buildSrc/.../Versions.kt` |
| `{BASE_APP_MODULES}` | The application module(s) at the bottom of the dependency tree (never themselves consumed by anything else) | your main app module name(s) |
| `{ORG_MODULE_CATALOG}` *(optional)* | A file mapping package prefixes → module name → git repo URL, if you maintain one | see "Organization-provided resources" below |
| `{ORG_BRANCHING_WORKFLOW}` *(optional)* | A shared doc/script your org already has for branch/version-bump/PR mechanics, if one exists | see below |
| `{ORG_CONSUMER_DETECTION}` *(optional)* | A script that finds every repo depending on a given module, if one exists | see below |
| `{ORG_ENGINEERING_STANDARDS}` *(optional)* | Your org's coding-standards doc, if one exists | see below |

None of the optional rows are required — Step 8/9 describe an inline fallback for each so
the skill is fully self-sufficient with nothing but a git host, an issue tracker, and a
checkout of the affected repos.

---

## Scope

Handles Android memory leak analysis from LeakCanary traces only.

**In scope:**
- App leaks (first-party code — matched via `{FIRST_PARTY_PACKAGE_PREFIXES}` — anywhere in
  the reference chain) — full analysis + fix
- Library leaks (third-party/framework-only chains) — flagged with a brief summary, no code fix

**Out of scope:**
- iOS memory leaks (separate tooling required)
- Native C++ memory issues (use Android Studio Memory Profiler)
- Java heap dumps / MAT analysis without a LeakCanary trace
- Non-LeakCanary traces (e.g. logcat OOM errors with no reference chain)
- General performance profiling (memory growth over time without a specific leak trace)

---

## Prerequisites

| Tool | Purpose | Verify | Install |
|------|---------|--------|---------|
| Issue-tracker access | Fetch tickets / search for open leak tickets (modes **Tracker tickets** and **Fetch all**) | Check whatever mechanism your environment uses to list connected integrations or tools | Connect your issue tracker (Jira, Linear, GitHub Issues, etc.) through whatever integration layer your agent runtime supports |
| A scripting runtime (e.g. `python3`) + a config-parsing library | Parse your project configuration and, if you maintain one, `{ORG_MODULE_CATALOG}` | e.g. `python3 -c "import yaml"` if using YAML | e.g. `pip3 install pyyaml` — substitute whatever your config format actually is (YAML/JSON/TOML) |
| `{GIT_HOST_CLI}` | Raise pull/merge requests (Step 9b) | e.g. `gh --version` / `glab --version` | e.g. `brew install gh && gh auth login` |

Issue-tracker access is required only for the **Tracker tickets** and **Fetch all** modes
(Step 2). For the **Manual trace** mode, no tracker access is needed — proceed directly to
Step 4.

---

## Organization-provided resources (all optional)

These let an organization plug in its own domain knowledge and shared conventions. None
are required to run this skill; each has a documented inline fallback.

| Resource | Purpose | If absent |
|------|---------|--------------|
| `{ORG_MODULE_CATALOG}` — a file mapping package-prefix → module name → git repo URL | Lets Step 4d/8a resolve which repo owns a given package without guessing | Derive the module/repo name by reasoning from the package name and your project configuration (Step 1); clone by convention (`{package-suffix}` → `{org-git-host}/{package-suffix}`) and confirm with the user's existing checkouts first |
| `{ORG_BRANCHING_WORKFLOW}` — a shared doc/script for branch creation, version bumps, and PR raising, if your org already has one shared across multiple AI skills | Keeps this skill consistent with whatever else in your org already automates branching/versioning | Follow the inline branching mechanics spelled out directly in Step 9 of this skill — they are a complete, self-sufficient version of the same contract |
| `{ORG_CONSUMER_DETECTION}` — a script that finds every repo depending on a given module | Speeds up Step 8b's consumer-module search | Do the equivalent search yourself: grep every known repo's dependency declarations (Gradle files, version catalogs) for the primary module's artifact coordinate |
| `{ORG_ENGINEERING_STANDARDS}` — your org's coding-standards doc | Keeps the generated fix idiomatic for your codebase | Fall back to general good practice for the language (Kotlin: coroutines over raw `Handler`/threads, safe calls over `!!`, immutable state where practical) |

---

## Step 1 — Load project configuration

Locate whatever file(s) your project/workspace uses to describe: the absolute path to the
Android project root, the list of top-level repos/modules already checked out locally, and
each module's build/test commands. The exact format is organization-specific (a
`workspace.yaml`, a `.env`, a `settings.gradle.kts` walk, etc.) — read whichever one your
environment actually has.

If you maintain `{ORG_MODULE_CATALOG}`, load it too — it maps every known package prefix to
its owning module, domain, and git repo URL. It is static, bundled reference data; don't
search for a different copy of it at runtime.

If no project configuration can be found at all, stop and tell the user what's missing —
you need at minimum a workspace root path and a way to discover which repos are already
cloned.

**Fail-fast auth check:** whatever raises the pull/merge request in Step 9b will itself
verify the git host CLI is authenticated, but that happens only after Steps 1–8's analysis
work is done. Check early too, so a missing auth doesn't waste that effort on a run that
was always going to fail at Step 9:

```bash
if ! {GIT_HOST_CLI} auth status >/dev/null 2>&1; then
  echo "⚠️ WARN: {GIT_HOST_CLI} is not authenticated — Step 9 (raise pull/merge requests)
           will fail. Authenticate now; continuing analysis in the meantime since a
           manual-trace or library-only run never reaches Step 9 and doesn't need it."
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "⚠️ WARN: python3 (or whatever scripting runtime your config parsing needs) was not
           found — parsing the project configuration and the version-bump logic in Step 9
           will fail. Install it before this run reaches Step 9."
fi
```

---

## Step 2 — Determine input mode

Decide which mode applies based on what the user provided:

| Mode | Trigger | Action |
|------|---------|--------|
| **Tracker tickets** | User pastes one or more issue-tracker URLs (e.g. a Jira `/browse/{ISSUE_TRACKER_PROJECT_KEY}-xxxx` link) | Fetch each ticket → extract the leak trace from its description |
| **Fetch all** | User says "fetch all memory leaks", "fetch android memory leak tickets", or similar | Query the tracker for all open tickets tagged `{LEAK_TICKET_LABEL}` under `{ISSUE_TRACKER_PROJECT_KEY}` |
| **Manual trace** | User pastes one or more raw LeakCanary trace blocks | Use provided text directly as leak input |
| **Vague memory report, no trace** | User describes memory growth with no trace/ticket (e.g. "the app feels slow after a while") | Reply: "I need a LeakCanary trace or a `{LEAK_TICKET_LABEL}` ticket to analyse this — general performance profiling without a trace is out of scope for this skill." Do not proceed. |

For the Tracker tickets and Fetch all modes, use whatever issue-tracker access is available
in your environment.

> **Resolving the right tool call** — the two calls you need are "get one issue by key" and
> "search issues by query." How you reach them depends entirely on your runtime:
> - **Claude Code with an Atlassian/Jira MCP server connected:** run `claude mcp list` to
>   find the connected server's name, then use the fully-qualified
>   `mcp__<server>__getJiraIssue` / `mcp__<server>__searchJiraIssuesUsingJql` form — never a
>   bare tool name, since more than one tracker-like server can be connected at once.
> - **Any other agent runtime:** use whatever API client, CLI (e.g. a `jira` or `linear`
>   CLI), or SDK call your environment exposes for the same two operations. Non-Jira
>   trackers (Linear, GitHub Issues, Azure Boards, …) will have their own query syntax —
>   translate the JQL shown in Step 3b into the equivalent for your tracker.
>
> Once resolved, call these `{issue_get_tool}` and `{issue_search_tool}` throughout Steps
> 3a and 3b below.
>
> If no issue-tracker access is available at all: stop and tell the user:
> "No issue-tracker integration is connected — paste the LeakCanary trace manually (use the
> Manual trace mode)."

For manual traces, proceed directly to Step 4.

---

## Step 3 — Fetch tickets and extract traces

### 3a — Single / multiple tracker URLs

For each URL provided, call `{issue_get_tool}` (resolved in Step 2) with the issue key
(e.g. `{ISSUE_TRACKER_PROJECT_KEY}-3269`).

**Filter rule:** A ticket is a memory leak ticket only if its title contains
`{LEAK_TICKET_LABEL}`. Skip any ticket whose title does NOT match this pattern; note it to
the user.

From each matching ticket, extract:
- `{ticket_id}` — the issue key
- `{ticket_title}` — summary/title field
- `{leak_trace}` — the LeakCanary trace block inside the description (look for a code block
  starting with `┬───` or `====` or `LEAK FOUND` or a stack of `├─` lines)
- `{reporter}` — the reporter's display name
- `{created_date}` — issue creation date
- `{impact_summary}` — `{ticket_title}` with the `{LEAK_TICKET_LABEL} ` prefix stripped.
  Example: title `{LEAK_TICKET_LABEL} signature: abc123` → `{impact_summary}` = `signature: abc123`.
  This is used verbatim in pull/merge-request descriptions as the identifying label next
  to the linked ticket ID.

### 3b — Fetch all memory leak tickets

Query your tracker with the equivalent of:

```
project = {ISSUE_TRACKER_PROJECT_KEY} AND summary ~ "{LEAK_TICKET_LABEL}" AND statusCategory != Done ORDER BY created DESC
```

(This is JQL, for a Jira tracker. Translate to your tracker's own query language if
different — e.g. a saved filter/label search in Linear or GitHub Issues.)

Use `{issue_search_tool}` (resolved in Step 2) with a reasonable page size (e.g. 50).

Log the matched tickets and proceed autonomously — analyse **all** of them, no confirmation:

```
ℹ️ AUTO: Found N open {LEAK_TICKET_LABEL} tickets — analysing all N:
  1. {ISSUE_TRACKER_PROJECT_KEY}-xxxx — [ticket title] (created: date)
  2. {ISSUE_TRACKER_PROJECT_KEY}-yyyy — [ticket title] (created: date)
  ...
```

If the query returns 0 tickets, print:

```
ℹ️ AUTO: No open {LEAK_TICKET_LABEL} tickets found on the {ISSUE_TRACKER_PROJECT_KEY} board. Nothing to analyse.
```

and stop — do not proceed to Step 4.

---

## Step 4 — Classify each trace

For every leak trace collected (from tickets or manual input), do the following:

### 4a — Identify leak type

Read the first line of the trace's reference path.

- **Library leak:** The trace's leaking object and the entire reference chain are in
  third-party or Android OS packages (e.g. `android.`, `androidx.`, `com.google.`,
  `com.squareup.`, `kotlin.`, `java.`). None of `{FIRST_PARTY_PACKAGE_PREFIXES}` appear as
  the *cause*.
- **App leak:** At least one frame in the reference chain matches
  `{FIRST_PARTY_PACKAGE_PREFIXES}`.

Flag library leaks clearly and treat them with an abbreviated summary (see Step 6 format).
Give full analysis only to app leaks.

If the trace is obfuscated (ProGuard/R8 class names like `a.b.c`) or otherwise too unclear to
confidently classify as Library vs. App:
```
⚠️ WARN: Leak type unclear from trace — will attempt a best-effort App-leak analysis using
         the reference chain shape alone. Manual code review recommended.
```
Proceed with Step 4b–5e using general null-out / weak-reference / lifecycle patterns rather
than package-based matching.

### 4b — Parse the reference chain (app leaks only)

From the LeakCanary trace, extract the reference chain in order:

```
[GC Root] → [Retaining Class A] → field/callback → [Class B] → ... → [Leaked Object]
```

For each link in the chain, record:
- The holding class and field/lambda name
- Whether it is a static field, instance field, or closure capture
- The package (first-party, Android framework, or third-party library)

### 4c — Identify the leaked object type

Classify the leaked object:
- **Activity / Fragment** — lifecycle object held beyond its lifetime
- **Context** — Activity context passed to a long-lived object
- **View / ViewBinding** — view reference held after `onDestroyView`
- **ViewModel / Presenter** — scoped object retained by a longer-lived owner
- **Service / Broadcast** — background component not released
- **Other** — document explicitly

### 4d — Module & repo verification (app leaks only)

From the reference chain, identify the first-party package(s) involved
(e.g. `{FIRST_PARTY_PACKAGE_PREFIXES}consultation`).

1. **Look up in `{ORG_MODULE_CATALOG}`** (if you maintain one) — find the module name and
   its git repo URL for each identified package. If absent, reason from the package name
   using your project configuration from Step 1 (e.g. `{prefix}consultation` →
   a module/repo plausibly named `consultation`).

2. **Check your project configuration** — confirm that the identified repo is already
   cloned in the workspace.

3. **If the repo is NOT in the workspace**, clone it automatically — do not wait for the user:

   ```bash
   git clone {repo_url} {workspace_root}/{module_name} \
     && echo "ℹ️ AUTO: cloned {module_name} → {workspace_root}/{module_name}" \
     || echo "❌ FATAL: could not clone {repo_url} — cannot analyse the leak without its source."
   ```

   If the clone fails, emit the `❌ FATAL:` line above and stop — this is a hard blocker, the
   module source is required to analyse and fix the leak. Otherwise continue.

4. Once all affected repos are present, continue to Step 5.

---

## Step 5 — Root cause analysis (app leaks only)

For each app leak, reason through:

### 5a — Reference chain narrative

Write 2–3 sentences explaining the chain in plain language:
*"X holds a strong reference to Y via field Z. Y is supposed to be released when [event],
but X outlives it because [reason]."*

### 5b — User journey / data flow

Identify which user journey or app flow can trigger this leak. Think through:
- Which screen or feature initialises the leaking object?
- What navigation event (back stack pop, tab switch, config change, process death) should
  release it but doesn't?
- Does the leak compound on repeated navigation (each traversal adds one instance)?

State this as: *"Leak is triggered when the user [navigates to / rotates / exits / …] the
[screen/feature] screen."*

### 5c — Root cause statement

One precise sentence naming the cause:
*"The root cause is [specific reason — e.g. `WorkManager` observer is registered on
`applicationContext` but stores a reference to `Activity` in a lambda]."*

### 5d — Steps to reproduce

```
Preconditions: [app version / account state / device condition]
Steps:
  1. [Navigate to / open ...]
  2. [Perform action ...]
  3. [Trigger navigation that should release the object]
  4. Repeat steps 2–3 N times to confirm compounding
Expected: Memory is released.
Actual:   LeakCanary fires [leaked object] trace.
```

### 5e — Fix approach (brief)

Describe the fix in 3–5 bullet points. Do NOT write the code here — it is implemented in Step 9.
Examples:
- "Use `WeakReference` for the Activity reference in `XManager`"
- "Remove the Broadcast observer in `onDestroyView` / `onStop`"
- "Replace `applicationContext`-scoped callback with a `LifecycleOwner`-aware observer"
- "Clear ViewBinding in `onDestroyView`"

---

## Step 6 — Generate Android_mem_leaks.md

Save to:
```
{workspace_root}/tcd_workspace/android-mem-leaks-{YYYYMMDD}/Android_mem_leaks.md
```

```bash
mkdir -p "{workspace_root}/tcd_workspace/android-mem-leaks-{YYYYMMDD}"
```

Use the exact structure defined in `references/leak_report_template.md` — load it now. Keep
each section short — the document is a reference for a developer, not a research paper.

---

## Step 7 — Print summary and continue

Print the document path and a short summary table for visibility, then proceed autonomously to
Step 8 — do **not** wait for review or approval:

```
✅ Android_mem_leaks.md generated at:
   {workspace_root}/tcd_workspace/android-mem-leaks-{YYYYMMDD}/Android_mem_leaks.md

Summary:
  • {N} app leaks analysed (High: x, Medium: y, Low: z)
  • {M} library leaks flagged (no code fix needed)

ℹ️ AUTO: analysis complete — implementing fixes and raising pull/merge requests (Steps 8–9).
```

Proceed directly to Step 8 without pausing.

---

## Step 8 — Resolve modules & detect consumers

### 8.0 — Local concurrency guard

If you follow `{ORG_BRANCHING_WORKFLOW}`, its own push-with-retry-on-conflict already
protects against two *different* engineers or machines racing on `{VERSION_TRACKER_FILE}`.
It does not protect against the narrower case of the *same* workspace running two
invocations of this skill at once (e.g. two parallel sessions on one machine), which can
race on local git state before either push ever reaches the tracker. Guard against that
narrower case only:

```bash
LOCK_FILE="{workspace_root}/.android-memoryleak-solver.lock"
if [ -f "$LOCK_FILE" ]; then
  LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0) ))
  if [ "$LOCK_AGE" -lt 3600 ]; then
    echo "❌ FATAL: Another android-memoryleak-solver run appears in progress in this workspace
             (lock age: ${LOCK_AGE}s). Wait for it to finish, or remove $LOCK_FILE if it crashed."
    exit 1
  fi
  echo "⚠️ WARN: Stale lock file (age ${LOCK_AGE}s) — removing and continuing."
fi
echo "$$" > "$LOCK_FILE"
```

**No `trap ... EXIT` here.** Each shell command you run is a separate process — a trap
registered in one would fire the instant that single command finishes, not when the whole
run (Steps 8–9, many separate commands) actually ends. Instead, remove `$LOCK_FILE`
explicitly at every point the run can end after this point:
- On success: as the last action of Step 9c, `rm -f "{workspace_root}/.android-memoryleak-solver.lock"`.
- On any `❌ FATAL:` stop reached after this step (Step 8a's null-repo guard, Step 9a's build-failure
  abort, Step 9b's version-authority or mid-cascade FATALs): run the same `rm -f` immediately before
  that stop, so a failed run doesn't leave a stale lock blocking the next one for up to an hour.

Prepare the branching variables for every repo touched by an **app leak**
(library leaks are skipped — they have no code fix).

Define a single feature slug for the whole run:
```
{feature-slug} = memory_leak-{ticket_id}
```
Where `{ticket_id}` is the tracker's issue key (e.g. `{ISSUE_TRACKER_PROJECT_KEY}-4221`).
For `manual` traces with no ticket, use `memory_leak-manual-{YYYYMMDD}`.

### 8a — Resolve the primary module(s)

For each app leak, the affected module and repo were already identified in Step 4d. From
your project configuration (match the first-party package to a module entry) record:
- `{primary_module}` — the Gradle module key (e.g. `teleconsultation`)
- `{repo_name}` — the repo directory under `{workspace_root}`
- `{namespace}` — the module namespace (e.g. `{FIRST_PARTY_PACKAGE_PREFIXES}teleconsultation`)
- `{test_command}` / `{build_command}` — from the module entry

**Null repo guard — check before proceeding:**

If the leak's package does not match any known module entry, `{repo_name}` is `null`. Do
not attempt file edits or pull/merge-request creation for that module with a null path:

```
If {repo_name} is null for this leak's module:
  Emit:
    ⚠️ WARN: Primary repo path is null — '{primary_module}' was not found in the project
             configuration. Attempting to clone via {ORG_MODULE_CATALOG} (or by convention)
             before proceeding.

  Attempt to clone the repo using the mechanism in Step 4d Step 1
  (match package prefix → module/repo name → clone from its git URL to
  {workspace_root}/{module_name}).

  If clone succeeds:
    Set {repo_name} to the cloned directory name and continue 8a normally for this module.

  If clone also fails:
    Print the Fix Approach bullets from Android_mem_leaks.md for this leak so a developer
    can apply the fix manually, then emit:
    ❌ FATAL: Cannot locate or clone primary repo for '{primary_module}' — pull/merge-request
             creation aborted for this leak. Apply the fix manually using the Fix Approach above.
    Skip this leak's module in Step 9 — never proceed with edits or PR creation against a
    null repo path. If every app leak in this run resolves to a null repo, remove the Step 8.0
    lock file (`rm -f "{workspace_root}/.android-memoryleak-solver.lock"`) and stop the entire
    run instead of invoking Step 9.
```

If several app leaks map to the **same** module, group them — that module is processed once.
If app leaks span **multiple** modules, each module is processed independently in Step 9
(library modules before `{BASE_APP_MODULES}`).

### 8b — Detect consumer modules

For each `{primary_module}` that is a **library** (publishes an artifact — not one of
`{BASE_APP_MODULES}`), find every repo depending on it so its version gets bumped in the
same run.

```bash
if [ -n "{ORG_CONSUMER_DETECTION}" ] && [ -f "{ORG_CONSUMER_DETECTION}" ]; then
  export SCAN_ROOT="{workspace_root}"
  export PRIMARY_REPO_NAME="{repo_name}"
  export PRIMARY_MODULE="{primary_module}"
  export PRIMARY_NAMESPACE="{namespace}"
  . "{ORG_CONSUMER_DETECTION}"   # sourced → sets $VALIDATED_CONSUMERS and $ORDERED_CONSUMERS
else
  # Inline fallback: grep every known repo's dependency declarations for this module's
  # published artifact coordinate (Gradle build files, version catalogs, lockfiles).
  echo "ℹ️ AUTO: no {ORG_CONSUMER_DETECTION} configured — searching repos under
           {workspace_root} directly for a dependency on {primary_module}'s artifact."
  # ... perform the equivalent search here; populate $VALIDATED_CONSUMERS / $ORDERED_CONSUMERS ...
fi

if [ -z "$VALIDATED_CONSUMERS" ]; then
  echo "⚠️ WARN: consumer detection ran but found zero consumers for {primary_module}. This
           may be correct (a genuinely unconsumed module) or a silent detection failure
           (missing tooling, unreadable project configuration). Verify manually before
           assuming this module truly has no consumers — a false empty here means real
           downstream consumers stay silently pinned to the old artifact after this run."
fi
```

Use `$ORDERED_CONSUMERS` (library consumers first, `{BASE_APP_MODULES}` last) as the Step 9
iteration order. Skip 8b entirely if `{primary_module}` is one of `{BASE_APP_MODULES}`.

---

## Step 9 — Implement the fix, bump versions & raise pull/merge requests

> ❌ **CRITICAL — non-negotiable rules. Violating any of these is a fatal error:**
>
> These rules exist because a leak fix inside a shared library module is never "one
> change" — it's a fix, a version bump on the module itself, a bump in the shared version
> catalogue, and a matching bump in every downstream consumer. Get the sequencing wrong and
> there's no compile error at review time — you get a dependency-resolution failure days
> later, for someone else, after merge.
>
> 1. **The shared version catalogue's repo gets exactly ONE branch (`{FIX_BRANCH_PREFIX}{feature-slug}`) for the entire run.**
>    - Create it once (from `{DEFAULT_BRANCH}`) before processing the primary module.
>    - The primary module version bump is the first commit; every consumer bump is another commit on the **same** branch.
>    - **Never create a new branch per consumer.** Result: exactly **ONE** pull/merge request for the version catalogue.
>
> 2. **All module versions MUST be read from `{VERSION_TRACKER_FILE}` on the `{VERSION_TRACKER_BRANCH}` branch — never from source.**
>    - Fetch + checkout that branch, read the current version, increment it, write it back, commit, push to `{VERSION_TRACKER_BRANCH}` immediately.
>    - Then switch to `{FIX_BRANCH_PREFIX}{feature-slug}` and apply that same new version to `{SHARED_VERSION_CATALOGUE}`.
>    - **Never read the starting version from `{SHARED_VERSION_CATALOGUE}` directly, and never from `{DEFAULT_BRANCH}`.**
>    - **Rationale:** `{SHARED_VERSION_CATALOGUE}` on `{DEFAULT_BRANCH}` reflects the last *merged* bump, not the last *raised* one. Two runs both reading the same starting version both compute the same next version, and the second merge silently overwrites the first. A dedicated always-current tracker file avoids that race.
>
> 3. **The primary module's own build file MUST be bumped to match `{SHARED_VERSION_CATALOGUE}`.**
>    - After computing the new version, update the module's own build file (the one that controls what version *it publishes*) to match.
>    - Verify the two agree before committing.
>    - Commit on `{FIX_BRANCH_PREFIX}{feature-slug}` alongside the leak fix.
>    - **Rationale:** CI publishes the artifact version from the module's own build file. If only `{SHARED_VERSION_CATALOGUE}` is bumped, consumers declare a dependency on the new version but CI publishes the old one — breaking resolution for every consumer after merge.
>
> 4. **Branch naming:**
>    - Primary, consumer, and version-catalogue repos: ONE branch each — `{FIX_BRANCH_PREFIX}{feature-slug}`. ONE pull/merge request each (`{FIX_BRANCH_PREFIX}...` → `{DEFAULT_BRANCH}`).
>    - Don't invent additional branch prefixes or intermediate branches — all commits go directly on `{FIX_BRANCH_PREFIX}{feature-slug}`.
>
> 5. **Consumer module processing order (sequential, not parallel):**
>    - Process consumers one at a time in `$ORDERED_CONSUMERS` order — library consumers first, `{BASE_APP_MODULES}` last.
>    - For each consumer: (a) checkout the SAME `{FIX_BRANCH_PREFIX}{feature-slug}` branch in the version-catalogue repo, (b) bump its version in `{VERSION_TRACKER_FILE}` → push to `{VERSION_TRACKER_BRANCH}` immediately, (c) bump its version in `{SHARED_VERSION_CATALOGUE}` → commit to the SAME branch, (d) if the consumer repo pins the version-catalogue repo as a submodule/dependency, point it at the updated commit.
>    - **(b) and (c) are MANDATORY even when the consumer has no code changes** — its downstream consumers must still resolve the updated dependency chain.
>
> 6. **`{VERSION_TRACKER_FILE}` is updated immediately — not when pull/merge requests merge.**
>    - `{SHARED_VERSION_CATALOGUE}` (on `{FIX_BRANCH_PREFIX}{feature-slug}`) lands on `{DEFAULT_BRANCH}` only when its PR merges; `{VERSION_TRACKER_FILE}` (on `{VERSION_TRACKER_BRANCH}`) is always current.

> **`{VERSION_TRACKER_FILE}` format** (for context when reading/parsing it): a Markdown
> table on `{VERSION_TRACKER_BRANCH}` with one row per module —
> `| {module} | {version} | {updated_by} |`. If `{ORG_BRANCHING_WORKFLOW}` parses this file
> with fixed patterns, keep the shape in sync with whatever it expects.

> ❌ **NO DELEGATION:** Implement the fix and raise pull/merge requests inline within this
> same run. Never hand this off to a separate agent, sub-agent, worker, or parallel
> session — each would create its own version-catalogue branch, producing exactly the
> multi-branch conflict Rule 1 exists to prevent.

### 9a — Apply the leak fix

For each app leak in `Android_mem_leaks.md`, apply its **Fix Approach** to the source under
`{workspace_root}/{repo_name}` — e.g. clear the ViewBinding in `onDestroyView`, wrap the
Activity reference in a `WeakReference`, unregister the observer/callback in the matching
lifecycle method. Follow `{ORG_ENGINEERING_STANDARDS}` if you have one; otherwise use
idiomatic Kotlin (coroutines over `Handler`, safe calls, no `!!`).

Run the module's `{build_command}` (e.g. `./gradlew :{primary_module}:assembleDebug`) before
anything is committed. On failure, emit `❌ FATAL: build failed for {primary_module} — cannot
raise a pull/merge request with a non-compiling fix.` and skip PR creation for this module
entirely — do not proceed to Step 9b for it. On success, continue.

Then run the module's `{test_command}` when one exists; on failure emit
`⚠️ WARN: unit tests failed — proceeding with pull/merge-request creation.` and continue.

**Leak fix verification:** LeakCanary runs in instrumented/release builds, not unit tests, so
`{test_command}` alone does not prove the leak is gone.
- If the leak path is reproducible in a test environment (e.g. a Fragment navigation loop),
  add an instrumented test that repeats the path and asserts LeakCanary detects no leak.
- If it isn't reproducible in tests, note in the PR description: "Leak fix verified manually:
  navigated [user journey] N times, no LeakCanary alert fired."

**Backward-compatibility check (library modules only):** If `{primary_module}` publishes an
artifact consumed by other modules (i.e. `$ORDERED_CONSUMERS` will be non-empty), check
whether the fix changed any **public** class, method signature, or field — not just internal
implementation details:
- Prefer narrowing the change to `private`/`internal` visibility if the public surface doesn't
  need to change for the fix.
- If a public signature change is unavoidable, note it explicitly in the PR description under a
  **Breaking Change** heading, and repeat the note in the version-catalogue PR description so
  consumer reviewers see it before merging: "This version bump also changes `{class}.{method}` —
  consumers calling that API directly will need to update their call site."
- If the module has a binary-compatibility tool already configured (e.g. Kotlin's
  binary-compatibility-validator), run it. Otherwise reason manually from the diff — do not
  assume such a tool exists.

### 9b — Branch, bump versions & raise pull/merge requests

If you have `{ORG_BRANCHING_WORKFLOW}`, follow it in full — branch creation, the two
version-file bumps, and PR creation. Otherwise, follow the inline mechanics below directly.
Either way, resolve these variables first (from Steps 3–8):

| Variable | Value |
|--------------------------------|---------------------|
| `{ISSUE_TYPE}` | `MEMORY_LEAK` |
| `{title}` | `Memory leak fix — {leaked_object}` |
| `{ticket_id}` | the leak's issue-tracker key (e.g. `{ISSUE_TRACKER_PROJECT_KEY}-3269`), or `manual` |
| `{leaked_object}` | the leaked class from the analysis (e.g. `ChatActivity`) |
| `{root_cause_summary}` | the one-line root cause from `Android_mem_leaks.md` |
| `{feature-slug}` | `memory_leak-{ticket_id}` (e.g. `memory_leak-{ISSUE_TRACKER_PROJECT_KEY}-4221`); for manual traces: `memory_leak-manual-{YYYYMMDD}` |
| `{primary_module}` / `{repo_name}` / `{namespace}` | from Step 8a |
| `{consumer_modules}` | `$ORDERED_CONSUMERS` from Step 8b |
| `{git_namespace}` | wherever your repos live on your git host (an org/group name) |
| `{test_status}` | from 9a — `"PASSED"` / `"FAILED — {test_command}"` / `"NOT RUN"` |

**Branch idempotency check (enforces Rule 1 above):**

`git checkout -b {FIX_BRANCH_PREFIX}{feature-slug}` in the version-catalogue repo (and in
the primary/consumer repos) fails outright if a local branch of that name already exists —
git's own uniqueness guarantee, so Rule 1 can never be silently violated by a *duplicate*
branch. What it doesn't handle is a clean **re-run** on the same `{feature-slug}` after a
prior attempt (partial failure, retry after fixing an error). Before creating the
version-catalogue branch, check:

```bash
if git -C "{version_catalogue_repo_path}" show-ref --verify --quiet "refs/heads/{FIX_BRANCH_PREFIX}{feature-slug}"; then
  echo "⚠️ WARN: branch {FIX_BRANCH_PREFIX}{feature-slug} already exists locally — this looks
           like a re-run. Reusing it rather than failing on 'git checkout -b'; verify no
           stale commits from an unrelated prior attempt remain on it before pushing."
fi
```

**Version-read verification (enforces Rule 2 above):**

Before executing the version bump, confirm the sequence actually:
1. Checks out `{VERSION_TRACKER_BRANCH}` in the version-catalogue repo.
2. Reads the module's current version from `{VERSION_TRACKER_FILE}` on that branch.
3. Increments it to compute the new version.
4. Writes the new version back to `{VERSION_TRACKER_FILE}` and pushes
   `{VERSION_TRACKER_BRANCH}` immediately.
5. Only then switches to `{FIX_BRANCH_PREFIX}{feature-slug}` and applies that same new
   version to `{SHARED_VERSION_CATALOGUE}`.

If any step deviates from this sequence (e.g. reads the starting version from
`{SHARED_VERSION_CATALOGUE}` or `{DEFAULT_BRANCH}` instead of the tracker, or applies the
`{SHARED_VERSION_CATALOGUE}` bump before the tracker file is pushed), emit:
```
❌ FATAL: did not follow the {VERSION_TRACKER_FILE} version-authority rule (Rule 2) —
         reading versions from the wrong source. Aborting to prevent a build-file ↔
         version-catalogue mismatch. Fix the branching workflow before re-running.
```
remove the Step 8.0 lock file (`rm -f "{workspace_root}/.android-memoryleak-solver.lock"`), and
stop the entire run before any version bump or PR creation — this is a structural problem with
the shared branching workflow, not specific to one leak, so no module in this run can proceed.

**Consumer null-path guard (applies to every consumer in `$ORDERED_CONSUMERS`):**

Before branching, editing, or raising a pull/merge request for each consumer module:
1. Verify its `{repo_name}` from your project configuration is non-null.
2. If null: attempt the same clone fallback as Step 8a (match the consumer's package prefix
   → module/repo name → clone from its git URL to `{workspace_root}/{module_name}`).
3. If the clone succeeds: set `{repo_name}` to the cloned directory and continue processing this
   consumer normally.
4. If the clone also fails, emit:
   ```
   ⚠️ WARN: Consumer '{consumer_module}' repo path is null and clone failed — skipping this
            consumer in the cascade. Its version WAS bumped in {VERSION_TRACKER_FILE}
            (Rule 5's tracker bump is unconditional) but no pull/merge request can be raised
            for it. Manually verify the repo exists and re-run the cascade for this consumer.
   ```
   Skip this consumer's file edits and PR creation, but continue to the next consumer in
   `$ORDERED_CONSUMERS` — a null path on one consumer must never abort the rest of the cascade.

5. After processing every entry in `$ORDERED_CONSUMERS`, if **all** of them were skipped for a
   null path (i.e. zero consumer PRs were raised despite `$ORDERED_CONSUMERS` being non-empty),
   surface this loudly in the Step 9c summary — the primary module's own PR is still valid and
   should still be raised, but a fully-failed cascade means every downstream consumer is left
   silently pinned to the old artifact and needs manual follow-up:
   ```
   ⚠️ WARN: Every consumer in this run's cascade ({consumer_count} total) hit a null-path skip —
            zero consumer pull/merge requests were raised. The primary module's PR is
            unaffected, but downstream consumers will not pick up this fix until their repos
            are located and the cascade is re-run manually for them.
   ```

**Shared build-config check (applies to the primary module and every consumer, if your repos
pin a shared build-config repo as a submodule or similar):**

Before pointing any repo's shared build config at the updated commit, confirm it's actually
wired that way in the first place — most repos in a given org tend to follow the same
convention, but this is a defensive guard for the rare repo that doesn't:

```bash
# Primary module:
if ! git -C "{workspace_root}/{repo_name}" submodule status {shared_build_config_dir} >/dev/null 2>&1; then
  echo "⚠️ WARN: {repo_name}'s shared build config is not wired as a submodule (or is a plain
           copied directory). The version bump was pushed to {VERSION_TRACKER_BRANCH}, but
           this repo will NOT auto-update via a submodule pointer commit. Verify how this
           repo pins its build config and sync it manually before merge."
fi

# Each consumer in $ORDERED_CONSUMERS — substitute {consumer_repo_name}, never {repo_name}:
if ! git -C "{workspace_root}/{consumer_repo_name}" submodule status {shared_build_config_dir} >/dev/null 2>&1; then
  echo "⚠️ WARN: {consumer_repo_name}'s shared build config is not wired as a submodule (or is
           a plain copied directory). The version bump was pushed to {VERSION_TRACKER_BRANCH},
           but this repo will NOT auto-update via a submodule pointer commit. Verify how this
           repo pins its build config and sync it manually before merge."
fi
```

If your org doesn't use a shared build-config repo/submodule at all, skip this check
entirely — it doesn't apply.

**Execution order:**
1. Resolve the version-catalogue repo path, git identity, `{git_namespace}`, and any
   credentials your `{GIT_HOST_CLI}` needs.
2. Primary module repo — create `{FIX_BRANCH_PREFIX}{feature-slug}`, apply the fix (9a), commit, push.
3. Raise the primary module pull/merge request (`{FIX_BRANCH_PREFIX}...` → `{DEFAULT_BRANCH}`).
4. If `{consumer_modules}` is non-empty: version-catalogue bump + its PR, then each consumer repo (branch, version bump, build-config repoint, PR) in `$ORDERED_CONSUMERS` order.
5. Repeat 2–4 for any additional affected module (multi-leak runs spanning modules).

**Mid-cascade failure guard:** `{VERSION_TRACKER_FILE}` is pushed to
`{VERSION_TRACKER_BRANCH}` *before* each consumer's own PR is confirmed raised (Rule 5's
tracker bump is unconditional). If PR creation then fails for a consumer (network,
permissions, branch conflict), do **not** continue to the next consumer in
`$ORDERED_CONSUMERS`. Emit:

```
⚠️ WARN: {consumer} version bumped in the tracker but pull/merge-request creation failed —
         the tracker is now ahead of raised PRs. Manually verify/re-raise the PR for
         {consumer} before any other run touches this module.
```

and stop the remaining cascade for this module (other independently affected modules from
Step 8a may still proceed).

### 9c — Final summary

Print the consolidated pull/merge-request list and the reviewer merge order — **the
version-catalogue PR first, then the primary module PR, then each consumer PR**. For each
module a PR was raised for, restate that its `{build_command}` passed (Step 9a already
gates PR creation on this — a PR only exists here because the build succeeded — but say so
explicitly for developer visibility):
```
✅ {primary_module}: build passed, pull/merge request raised → {primary_pr_url}
```
Then remove the Step 8.0 lock file: `rm -f "{workspace_root}/.android-memoryleak-solver.lock"`.

---

## Worked example

See `references/worked_example.md` for a full abbreviated walkthrough. Note that it was
written against one organization's specific tooling — read it for the *shape* of a
multi-repo cascade (one leak → N pull/merge requests, in what order, with what content),
not for its literal file/branch names, which follow that organization's own
`{VERSION_TRACKER_FILE}` / `{FIX_BRANCH_PREFIX}` / repo-naming conventions.

---

## Handling edge cases

- **No trace in ticket:** Note "No LeakCanary trace found in {ticket_id}" in the document and
  skip that ticket — do not pause to request input.
- **Truncated trace:** Work with what is available; label uncertain parts of the chain clearly.
- **Multiple traces for the same leaked type:** Group them as one leak entry; note that multiple
  tickets reference the same root cause.
- **Trace without any first-party frames:** Classify as library leak unless context strongly
  suggests first-party code is the trigger.
