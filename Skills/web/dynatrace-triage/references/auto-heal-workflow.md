# Auto-Heal Workflow (Mode 3)

Batch pipeline: pick a data source, pull errors, hard-filter to 1st-party
eligible errors, diagnose all of them, show the plan, THEN fix — with NO
human approval gate on the fixing itself (the confidence rules ARE that
gate). Every auto-fixed error produces exactly one MR. Low-confidence errors
are report-only. All outcomes land in the attribution registry
([registry-format.md](./registry-format.md)) and a readable visual board
([visualization.md](./visualization.md)).

Command: `dynatrace_triage heal [--csv <path> | --source token|browser] [--repo <path>] [--min-users 100] [--dry-run]`

Read before acting: [live-pull.md](./live-pull.md), [token-pull.md](./token-pull.md),
[eligibility.md](./eligibility.md), [visualization.md](./visualization.md),
[architecture-rules.md](./architecture-rules.md), [mr-format.md](./mr-format.md),
[sourcemap-preflight.md](./sourcemap-preflight.md).

Set once per run:

```text
run_id   = heal-<YYYY-MM-DD>-<n>
registry = ~/.claude/dynatrace-triage-workspace/<repo-name>/registry.json
```

## Phase -1: Data source selection

**Before any Dynatrace access happens**, determine the acquisition path:

- `--csv <path>` given → use it directly (fallback path, unchanged from v3).
- Otherwise, if `--source` is given (`token` or `browser`), use it.
- Otherwise, **ask**: "Pull live from Dynatrace using an API token, or via
  the Chrome browser session? (or provide a CSV export instead)" — this is a
  real choice with real trade-offs (token needs `DT_API_TOKEN` + an unproven
  schema for browser data; browser needs an authenticated Chrome tab but no
  new credentials) and must not be silently defaulted.

Route to [token-pull.md](./token-pull.md) or [live-pull.md](./live-pull.md)
accordingly. Both must emit the same canonical row JSON
([eligibility.md](./eligibility.md)'s schema) so everything downstream is
identical regardless of path. If the chosen path hits a hard blocker (token
rejected, schema undiscoverable, no browser session), report it and offer to
fall back to one of the other two — never silently guess.

## Phase 0: Preconditions

```bash
git -C <repo> status --short          # must be empty
git -C <repo> checkout master
git -C <repo> pull origin master
git -C <repo> rev-parse HEAD          # base SHA
command -v glab                       # note if missing — do NOT abort
```

Rules:

- **Dirty tree is the ONLY allowed human stop in Mode 3** (besides the Phase
  -1 source choice, which is a legitimate up-front decision, not a stop) —
  ask stash/abort.
- `glab` missing does NOT abort the run: fixes are still made and pushed;
  MRs become `auto-fixed-mr-pending` with the exact `glab mr create` command
  recorded (see Phase 2B step 7).
- Initialize the registry immediately:
  `python3 scripts/registry.py init <registry> --run-id <run_id> --csv <source-description> --base-sha <sha> --repo <repo> --min-users <n>`
- Run the sourcemap preflight ([sourcemap-preflight.md](./sourcemap-preflight.md))
  and record the result:
  `python3 scripts/registry.py preflight <registry> --run-id <run_id> --result "<result>"`

## Phase 1: Build the work queue

Acquire rows per the Phase -1 choice (browser: [live-pull.md](./live-pull.md);
token: [token-pull.md](./token-pull.md); csv: existing export), scoped to the
**7-day rolling window** (widened from the original 3 days), then:

```bash
python3 scripts/eligibility.py <csv-or-json-flag> --min-users <n> --first-party-domain <domain> --out <workspace>/queue-<run_id>.json
```

Register EVERY row up front so even a crashed run leaves a record:

- `skipped-3rd-party` rows → `registry.py update … --status skipped-3rd-party --note "<matched signal(s)>"`
  (this is a HARD exclusion at extraction time now — never "suspected"; see
  [eligibility.md](./eligibility.md)).
- `skipped-below-threshold` rows → `registry.py update … --status skipped-below-threshold --note "<users> < <min_users>"`.
- eligible rows are processed in queue order (users desc) in Phase 2A.

**Re-run dedupe:** before processing an eligible error, check the registry —
if it is already `auto-fixed`/`auto-fixed-mr-pending` with an open MR, skip it
(status unchanged, note "already has open MR from run <id>").

`--dry-run`: stop after Phase 2A + the pre-fix visualization. No branches, no
edits, no MRs, no Phase 2B.

## Phase 2A: Diagnose all (no side effects)

For every eligible error, in queue order — **no branching, fixing, or
committing yet**:

### 1. Evidence, symbolication, diagnosis

Reuse Mode 1 [workflow.md](./workflow.md) Steps 2–4 verbatim: evidence order,
sourcemap deobfuscation ([sourcemaps.md](./sourcemaps.md)), and the architect
diagnosis. Produce `symptom`, `trigger`, `root_cause`,
`product_runtime_explanation`.

### 2. Confirm 1st-party (evidence stage — second, stricter gate)

Apply [eligibility.md](./eligibility.md) Stage 2 to the resolved frames.
Pure vendor/extension stack → `registry.py update … --status skipped-3rd-party --note "<frame evidence>"`,
continue to next error (this row already passed stage 1's extraction-time
check; stage 2 can still catch it from real stack evidence).

### 3. Confidence gate — decide the PLANNED action only

Apply [architecture-rules.md](./architecture-rules.md) scoring:

- **Planned: Auto-Fix** iff source confidence is NOT low AND fix confidence
  is high, or medium with explicit assumptions (assumptions must be written
  down now — they go into the MR body and registry entry in Phase 2B).
- **Planned: Report-Only** otherwise — write the triage writeup now (symptom,
  trigger, ranked root-cause candidates, which signals were missing, what
  evidence would raise confidence).

Record the planned action and diagnosis in memory/a scratch structure for the
visualization step — do not update the registry to a terminal status yet
(Phase 2B does that once the action actually executes, so the registry
reflects reality, not intent).

## Visualize (between 2A and 2B)

Render the pre-fix triage board per [visualization.md](./visualization.md):
every diagnosed candidate with its hypothesis, confidence, and planned
action, PLUS the hard-excluded (3rd-party) and below-threshold rows for
auditability. This is a preview — nothing has been fixed yet.

If `--dry-run`, stop here.

## Phase 2B: Execute planned actions

For each error, in the same queue order, **now** take the action planned in
2A:

### Report-Only candidates

`registry.py update … --status reported --note "<writeup from 2A>"`. No
branch, no MR.

### Auto-Fix candidates

#### 1. State isolation — always start clean

```bash
git checkout master
git fetch origin master
git reset --hard origin/master
git clean -fd
```

#### 2. Branch from latest master — verified

```bash
git fetch origin master
git checkout -B fix/error-<id>-<kebab-context> origin/master
git merge-base --is-ancestor origin/master HEAD || echo "BRANCH PROVENANCE FAILURE"
git rev-parse origin/master               # branch_point_sha for the registry
```

Every fix branch is provably cut from up-to-date `origin/master` — never from
a previous fix branch. Record `--branch` and `--branch-point-sha` when
updating the registry.

Then apply the smallest correct fix per [workflow.md](./workflow.md) Step 5
and [error-patterns.md](./error-patterns.md), using the diagnosis already
produced in Phase 2A (do not re-diagnose from scratch).

#### 3. Test gate — mandatory before any MR

1. **Reproduce**: the new/updated spec must cover the failure path — it should
   fail against the pre-fix code and pass with the fix. When practical, verify
   by stashing the fix (`git stash`), running the spec (expect red), then
   restoring (`git stash pop`, expect green). When reproduction isn't
   feasible (e.g. timing-dependent), state why explicitly in the MR body.
2. **Lint**: `pnpm eslint <changed files>` — clean.
3. **Tests**: `pnpm test -- --include="**/<changed-spec>.spec.ts" --watch=false --browsers=ChromeHeadlessCI`
   — green, plus the specs of directly-touched sibling components.

Failure policy:

- On lint/test failure: re-diagnose and retry ONCE (adjust fix or test).
- Second failure: delete the branch
  (`git checkout master && git branch -D <branch>`), downgrade to
  `reported` with the failure log excerpt in the writeup.
- Test-infra failure unrelated to the change (e.g. headless Chrome missing):
  counts against the run, not the error — note it globally, fall back to
  lint-only, mark the registry note `tests-not-run: <reason>`, and surface it
  prominently in the run report. Never silently skip tests.

#### 4. Commit, push, MR

```bash
git add <changed files>
git commit -m "<scope>: <summary> (dynatrace <error_id>)"
git push -u origin fix/error-<id>-<kebab-context>
glab mr create --source-branch fix/error-<id>-<kebab-context> --target-branch master \
  --title "fix(<scope>): <short summary> (<error_id>)" \
  --description "<mr-format.md body + Auto-Heal Attribution block>" \
  --label "auto-heal,dynatrace-triage"
```

- MR body: canonical [mr-format.md](./mr-format.md) body **plus** the
  Auto-Heal Attribution block (marker, run id, confidences, duplicate-group
  cross-references). No auto-merge — MRs await human review; "auto-remediated"
  means the fix and MR required no human authoring.
- Success → `registry.py update … --status auto-fixed --mr-url <url> --branch <b> --branch-point-sha <sha> --confidence-source <s> --confidence-fix <f>`
- `glab` missing → push anyway, record the ready-to-run `glab mr create`
  command in the registry note, status `auto-fixed-mr-pending`.

### Failure isolation

Any unexpected failure while processing an error (sourcemap fetch, tooling
crash, git conflict): capture a one-line summary, `registry.py update … --status reported --note "pipeline-error: <summary>"`,
then continue with the next error — the state-isolation step at the top of
each Auto-Fix iteration cleans up whatever was left. **One error's failure
never aborts the batch.**

## Phase 3: Finalize

```bash
git checkout master && git reset --hard origin/master
python3 scripts/registry.py finalize <registry> --run-id <run_id>
python3 scripts/registry.py report   <registry> --run-id <run_id>
```

Redeploy the visualization Artifact per [visualization.md](./visualization.md)'s
post-run board (same URL, updated to show actual outcomes).

Print the markdown report inline. It must show:

- remediation rate vs the **75% target** with an explicit verdict
- MR coverage of auto-fixed (must be 100%; less is a defect line)
- all outcome tables (auto-fixed / reported / skipped-3rd-party /
  skipped-below-threshold) so the pulled row count reconciles visibly
- blockers (e.g. `glab` missing) at the top

## Phase 4: Resolution verification (later runs)

When a heal run happens against a fresh pull:

```bash
python3 scripts/registry.py verify <registry> --run-id <new_run_id> --fresh-csv <fresh-source>
```

- prior `auto-fixed*` entry absent from the fresh pull → `resolved-verified`
- still present → `regressed-or-unmerged` (check `glab mr view <url>` to tell
  which: unmerged MR means the fix hasn't shipped — not a regression)

This closes the attribution lifecycle: error → branch → MR → verified
resolution.
