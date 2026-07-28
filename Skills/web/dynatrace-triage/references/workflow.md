# Workflow

## Contents

- [Mode 1: High-Confidence Fix](#mode-1-high-confidence-fix)
- [Mode 2: Strategic Summary](#mode-2-strategic-summary)

## Mode 1: High-Confidence Fix

### Step 0: Detect git provider and sync base branch

```bash
git branch --show-current
git remote -v
git remote get-url origin
git status --short
git checkout master
git pull origin master
git log --oneline -1
```

Rules:
- identify forge from `git remote get-url origin`
- stop on dirty-tree ambiguity or pull failure

### Step 1: Parse the CSV row

Normalize the exact row for the requested `error_id`.

Prefer using `scripts/parser.py` when helpful.

### Step 2: Build evidence before fixing

Collect evidence in this order:
1. exact runtime error text
2. stack trace signature
3. top pages and teams
4. chunk or frame hints
5. matching source candidates
6. existing tests and nearby similar components
7. why the chosen source candidate is the best fit

Before patching, write down:
- `symptom`
- `trigger`
- `root_cause`
- `product_runtime_explanation`

### Step 3: Deobfuscate and locate source

Use these signals in order and stop when at least 2 align:
1. function name from stack trace
2. chunk/module mapping
3. error property or method name
4. top-page routing/module match
5. similar known pattern in sibling components

If the stack points to minified `<your-domain>/resources/*.js` bundles and source confidence remains low, read [sourcemaps.md](./sourcemaps.md) and use the sourcemap workflow to deobfuscate the frame before claiming high confidence.

### Step 4: Diagnose as senior frontend architect

Evaluate:
- is the missing value actually optional?
- is this state initialization?
- is this ordering/lifecycle?
- is this SSR/browser environment?
- is this a parent/child or service/component contract issue?
- is the defect duplicated nearby?

### Step 5: Apply the smallest correct change

When editing:
1. read the whole target file
2. read the spec file and sibling implementation if needed
3. apply the smallest change that fixes the root cause
4. **blast radius check**: if the change touches a shared utility, service,
   or component used by multiple pages/modules — `git grep "import.*<name>"`
   to find every caller, and check whether the change could affect them
   (signature change, behavior change). If risky, note it explicitly in the
   MR body ("this utility is used by X, Y, Z — verify no regressions").
   Page-specific components usually don't need this.
5. before adding tests, read the existing spec file in full — if a test
   already covers the failure path (even partially), update it rather than
   duplicating
6. add or update focused tests for:
   - reproduced failure path
   - normal success path
   - boundary/null/undefined path when relevant
   - regression-guard path where unintended behavior could silently change
7. **verify build and typecheck before delivery** — lint and unit tests
   alone can miss a type error or build break outside the touched spec
   file; see the exact commands in Step 8 (`pnpm build`/`tsc --noEmit`
   alongside `pnpm eslint`/`pnpm test`). Do not proceed to Step 6's review
   summary until the build is clean.

### Step 6: Architect review summary before delivery

Produce a structured fix summary containing:
- `error_id`
- `error_message`
- `severity`
- `signal`
- `affected_users`
- `source_confidence`
- `fix_confidence`
- `symptom`
- `trigger`
- `root_cause`
- `product_runtime_explanation`
- `why_this_fix_is_correct`
- `why_alternatives_are_weaker`
- `behavior_changed`
- `behavior_unchanged`
- `hidden_breakpoints`
- `regression_risks`
- `related_modules_or_components_to_audit`
- `systemic_follow_up`
- `files_changed`
- `tests_added_or_updated`
- `commit_message`

`systemic_follow_up` should contain:
- nearby components to inspect
- repeated patterns in the module
- lint rule/helper/shared abstraction opportunities
- whether the fix should become a reusable pattern

### Step 7: Human approval gate

```text
Are you satisfied with this fix? (yes/no)
- If yes: I will create a git branch, apply the fix, validate it, commit it, push it, and open a PR/MR automatically.
- If no: I will propose an alternative approach.
```

### Step 8: Branch, validate, commit, push

```bash
git checkout -b fix/error-${error_id}-${error_context}
pnpm eslint <changed-files>
pnpm build   # or `tsc --noEmit` / the project's typecheck script — lint and
             # unit tests alone can miss a type error or build break outside
             # the touched spec file
pnpm test -- --include="**/<changed-spec>.spec.ts" --watch=false --browsers=ChromeHeadlessCI
git status --short
git add <changed-files>
git commit -m "<scope>: <summary>"
git push -u origin fix/error-${error_id}-${error_context}
```

### Step 9: Create MR/PR

Use the canonical body in [mr-format.md](./mr-format.md).

Provider preference:
- GitLab: `glab mr create`
- GitHub: `gh pr create`

If the correct CLI is missing, stop and report the blocker.

## Mode 2: Strategic Summary

Group duplicates, identify shared failure modes, and recommend durable architectural follow-up.
