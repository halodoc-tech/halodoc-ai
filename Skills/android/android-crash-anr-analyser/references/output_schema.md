# Output schemas

**Contents:** [Why this file exists](#why-this-file-exists) · [sprint_plan.json](#sprint_planjson) ·
[test_cases.json](#test_casesjson) · [Run result (exit contract)](#run-result-exit-contract) ·
[Console summary](#console-summary)

## Why this file exists

Three files this skill writes are read by machines, not just people: `sprint_plan.json` and
`test_cases.json` feed Step 7 (and any other coding tool you point at them), and the run
result is what CI parses to decide what happened. A field that is present-but-empty fails
silently downstream, so the shapes are fixed here. Decision rules (how many tasks, which test
cases are mandatory) live in `../SKILL.md` Step 6; this file is only the literal shape.

All three go in `{workspace_root}/{OUTPUT_DIR}/{feature-slug}/`.

---

## sprint_plan.json

```json
{
  "_meta": {
    "feature": "{Crash | ANR} fix: {title}",
    "feature_slug": "{feature-slug}",
    "plan_source": "android-crash-anr-analyser",
    "issue_id": "{issue_id}",
    "issue_uri": "{issue_uri or empty}",
    "analysis_doc_path": "{OUTPUT_DIR}/{feature-slug}/CrashAnalysis_{ShortTitle}.md",
    "primary_module": "{module}",
    "primary_repo_name": "{repo or null}",
    "primary_namespace": "{namespace}",
    "primary_is_app": false,
    "primary_catalogue_key": "{version key in SHARED_VERSION_CATALOGUE, or null}",
    "generated_at": "YYYY-MM-DD",
    "modules_missing": false,
    "consumer_modules": [
      { "module": "{name}", "repo_name": "{repo}", "build_file": "{path}", "catalogue_key": "{key}", "is_app": false }
    ],
    "open_questions": []
  },
  "dev_workflow": {
    "step_1_edit":    "Edit files in {workspace_root}/{repo_name}/ on {FIX_BRANCH_PREFIX}{feature-slug}",
    "step_2_compile": "{compile_command or null}",
    "step_3_test":    "{test_command or null}"
  },
  "tasks": [
    {
      "id": "TASK-001",
      "title": "{specific fix title}",
      "priority": 1,
      "status": "TODO",
      "rationale": "{why this removes the root cause — maps to Fix Approach}",
      "issue_class": "{C1–C10 / C6-sub-type, or the exception class}",
      "is_symptom_guard": false,
      "guard_justification": null,
      "files": [
        {
          "class": "{root_package}.{simple_name}",
          "path": "{repo-relative path}",
          "action": "modify",
          "changes": [
            "{Fix Approach step 1 — specific enough to implement without the document}",
            "{step 2}"
          ]
        }
      ],
      "feature_flag": null,
      "strings": {},
      "test_ids": ["TC-001", "TC-002", "TC-003"],
      "notes": "{log signal from Verification}"
    }
  ]
}
```

- `strings`: `{ "resource_key": { "en": "…", "<locale>": "…" } }` — every locale the app
  ships, only when the fix adds user-facing text.
- `is_symptom_guard` / `guard_justification`: set when the task is a guard rather than a
  root-cause fix (`../SKILL.md` Step 4f); the justification has three parts — why not at
  source, fallback behaviour, observability.
- `modules_missing: true` permits an empty `files[].path`; nothing else does.

---

## test_cases.json

```json
{
  "_meta": {
    "feature": "{Crash | ANR} fix: {title}",
    "feature_slug": "{feature-slug}",
    "generated_at": "YYYY-MM-DD",
    "total_cases": 3,
    "breakdown": { "unit": 2, "negative": 1, "integration": 0 }
  },
  "test_cases": [
    {
      "id": "TC-001",
      "title": "{scenario} — failure no longer occurs",
      "type": "unit",
      "priority": "P0",
      "role": "reproduction",
      "task_ref": "TASK-001",
      "class_hint": "{simple_name}Test",
      "method_hint": "{scenario}_doesNotCrash",
      "uses_test_dispatcher": false,
      "preconditions": ["{the state from the hypothesis}"],
      "steps": ["Given: {state}", "When: {call}", "Then: {safe outcome}"],
      "expected_result": "No {ExceptionClass | main-thread block}. {Defined outcome}.",
      "fails_without_fix": true
    },
    {
      "id": "TC-002",
      "title": "{edge case}",
      "type": "negative",
      "priority": "P1",
      "role": "edge_case",
      "task_ref": "TASK-001",
      "class_hint": "{simple_name}Test",
      "method_hint": "{edgeCase}_handledSafely",
      "uses_test_dispatcher": false,
      "preconditions": ["{edge precondition}"],
      "steps": ["Given: …", "When: …", "Then: …"],
      "expected_result": "{defined outcome}",
      "fails_without_fix": false
    },
    {
      "id": "TC-003",
      "title": "Existing behaviour unchanged",
      "type": "unit",
      "priority": "P0",
      "role": "regression",
      "task_ref": "TASK-001",
      "class_hint": "{simple_name}Test",
      "method_hint": "{happyPath}_worksAsBefore",
      "uses_test_dispatcher": false,
      "preconditions": ["{normal state}"],
      "steps": ["Given: …", "When: …", "Then: …"],
      "expected_result": "{existing behaviour preserved}",
      "fails_without_fix": false
    }
  ]
}
```

For ANRs, TC-001 has `"uses_test_dispatcher": true` and its `expected_result` states which
dispatcher the blocking work must now run on. `fails_without_fix` is the *claim*; whether it
was actually observed is `build.reproduction_verified` in the run result (`../SKILL.md` Step 7).

---

## Run result (exit contract)

Printed as the last fenced `json` block of every run — success or `❌ FATAL` — and written to
`run_result.json` when the output directory exists. Fields that do not apply are `null` or
`[]`, never omitted, so a parser can rely on every key.

```json
{
  "skill": "android-crash-anr-analyser",
  "status": "SUCCESS | PARTIAL | ANALYSIS_ONLY | FATAL",
  "mode": "A | B | C",
  "action": "FIX | ANALYSE",
  "issue": {
    "type": "CRASH | ANR",
    "id": "{issue_id}",
    "uri": "{issue_uri or null}",
    "title": "{title}",
    "app": "{APP or null}",
    "events": "{number | \"unavailable\" | \"N/A (manual input)\"}",
    "users": "{number | \"unavailable\" | \"N/A (manual input)\"}",
    "first_seen": "{version or null}",
    "last_seen": "{version or null}"
  },
  "analysis": {
    "feature_slug": "{feature-slug}",
    "root_location": "{root_class}.{root_method}:{root_line}",
    "issue_class": "{C1–C10 | C6-IO | C6-LOCK | C6-BINDER | C6-HEAVY | null}",
    "origin": "APP | SDK | OTHER",
    "hypothesis": "{the confirmed one-sentence root cause}",
    "confidence": "HIGH | MEDIUM | LOW",
    "obfuscated_frames": false,
    "symptom_guard_used": false,
    "regression_risk": "HIGH | MEDIUM | LOW",
    "release_verdict": "SAFE TO RELEASE | NEEDS FEATURE FLAG | NEEDS HOTFIX"
  },
  "build": {
    "primary_module": "{module}",
    "repo_name": "{repo or null}",
    "compile_status": "PASSED | FAILED | NOT RUN",
    "compile_attempts": 1,
    "test_status": "{test_status string}",
    "reproduction_verified": "true | false | null (null when Step 7 did not run)"
  },
  "versions": [
    { "module": "{module}", "from": "{old}", "to": "{new}", "tracker_pushed": true, "reused_existing": false }
  ],
  "pull_requests": [
    { "merge_order": 1, "role": "catalogue | primary | consumer | base_app", "repo": "{repo}", "branch": "{branch}", "url": "{url}", "reused_existing": false }
  ],
  "consumers": {
    "detected": ["{module}"],
    "skipped": [ { "module": "{module}", "reason": "{why}" } ]
  },
  "artifacts": {
    "analysis_doc": "{path or null}",
    "sprint_plan": "{path or null}",
    "test_cases": "{path or null}"
  },
  "warnings": ["{each ⚠️ WARN line, verbatim}"],
  "fatal": null
}
```

**Status meanings:**

| Status | Meaning |
|---|---|
| `SUCCESS` | Fix committed, compile passed, `reproduction_verified: true`, every expected PR raised (or reused) |
| `PARTIAL` | PRs raised, but something is incomplete: compile or tests failing, reproduction not verified, a consumer skipped, or a mid-cascade stop (`warnings` then holds a `tracker ahead: …` line) |
| `ANALYSIS_ONLY` | Analysis artifacts written, deliberately no code change: `ACTION=ANALYSE`, primary repo not on disk and not clonable, obfuscated root frame, SDK/OTHER with no first-party fix site, already fixed |
| `FATAL` | A hard blocker stopped the run; `fatal` holds the `❌ FATAL` message and every artifact produced before it is still listed |

`reproduction_verified` is a JSON boolean or `null`; `mode` is `null` only when Step 0 could
not determine one; `action` is always present, also on a
`FATAL` from Step 0 (the value chosen by the ACTION rules, or `null` if the run stopped before
it was chosen). On `ACTION=ANALYSE`, `versions` and `pull_requests` are `[]`.

**FATAL shape (example: no selector).** Every key is still present:

```json
{
  "skill": "android-crash-anr-analyser", "status": "FATAL", "mode": null, "action": "ANALYSE",
  "issue": { "type": "CRASH", "id": null, "uri": null, "title": null, "app": null,
             "events": null, "users": null, "first_seen": null, "last_seen": null },
  "analysis": null, "build": null, "versions": [], "pull_requests": [],
  "consumers": { "detected": [], "skipped": [] },
  "artifacts": { "analysis_doc": null, "sprint_plan": null, "test_cases": null },
  "warnings": [],
  "fatal": "❌ FATAL: No issue selector provided. Set one of APP=<key>, ISSUE_ID=<id> APP=<key>, MANUAL_ISSUE_FILE=<path>, MANUAL_ISSUE_TEXT=<trace>, or paste a stack trace / ANR dump, or name an app from APP_REGISTRY."
}
```

`analysis` and `build` are `null` (not omitted) when the run stopped before those steps.

---

## Console summary

Printed by `../SKILL.md` Step 9 just before the run result:

```
✅ Run complete.   (or: ℹ️ Analysis complete — ACTION=ANALYSE, no changes made.)

Feature slug: {feature-slug}
Issue:        {title}  ({issue_uri or "manual input"})
Class/Origin: {issue_class} / {crash_origin} — {crash_origin_reason}
Hypothesis:   {one sentence}  [confidence: {confidence}]
Impact:       {impact_summary}   Versions: {first_seen} → {last_seen}
Tests:        {test_status}   Reproduction verified: {true|false|n/a}
Verdict:      {release_verdict}   Regression risk: {regression_risk}

Outputs: {workspace_root}/{OUTPUT_DIR}/{feature-slug}/
  CrashAnalysis_{ShortTitle}.md · sprint_plan.json ({N} tasks) · test_cases.json ({N} cases) · run_result.json

PRs (merge in this order):
  1. {catalogue PR}   2. {primary PR}   3. {consumer PRs…}   4. {base app PRs}
  (ACTION=ANALYSE: "none — re-run with ACTION=FIX to apply the fix")
```

Follow it with the origin follow-ups for **SDK** and **OTHER** issues (Step 9).
