# Output schemas

**Contents:** [Why this file exists](#why-this-file-exists) · [sprint_plan.json](#sprint_planjson) ·
[test_cases.json](#test_casesjson) · [Run result (exit contract)](#run-result-exit-contract)

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
    "generated_at": "YYYY-MM-DD",
    "modules_missing": false,
    "consumer_modules": [
      { "module": "{name}", "repo_name": "{repo}", "build_file": "{path}", "is_app": false }
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
          "class": "{root_class}",
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
      "class_hint": "{root_class}Test",
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
      "class_hint": "{root_class}Test",
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
      "class_hint": "{root_class}Test",
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
dispatcher the blocking work must now run on.

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
    "test_status": "{test_status string}"
  },
  "versions": [
    { "module": "{module}", "from": "{old}", "to": "{new}", "tracker_pushed": true }
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
| `SUCCESS` | Fix committed, compile passed, every expected PR raised (or reused) |
| `PARTIAL` | PRs raised, but something is incomplete: compile or tests failing, a consumer skipped, or a mid-cascade stop |
| `ANALYSIS_ONLY` | Analysis artifacts written, deliberately no code change (obfuscated root frame, SDK/OTHER with no first-party fix site, already fixed) |
| `FATAL` | A hard blocker stopped the run; `fatal` holds the `❌ FATAL` message and every artifact produced before it is still listed |
