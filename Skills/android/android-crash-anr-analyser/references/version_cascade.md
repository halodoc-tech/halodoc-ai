# Version cascade: branches, bumps, pull/merge requests

**Contents:** [Why this file exists](#why-this-file-exists) ·
[1. Non-negotiable rules](#1-non-negotiable-rules) ·
[2. Shared helpers](#2-shared-helpers) ·
[3. Repo sync and fix branch](#3-repo-sync-and-fix-branch) ·
[4. What a re-run reuses](#4-what-a-re-run-reuses) ·
[5. Primary repo: commit the fix](#5-primary-repo-commit-the-fix) ·
[6. Library modules: version bump](#6-library-modules-version-bump) ·
[7. Primary PR, then catalogue PR](#7-primary-pr-then-catalogue-pr) ·
[8. Each consumer](#8-each-consumer) ·
[9. Failure recovery: tracker ahead of PRs](#9-failure-recovery-tracker-ahead-of-prs)

## Why this file exists

A fix in a shared library is never one change. It is the fix, a version bump on the module,
a bump in the shared version catalogue, and a bump in every downstream consumer. Get the
sequence wrong and nothing fails at review: a dependency resolution fails days later, for
someone else, after merge. These mechanics only run on the `ACTION=FIX` path, so they live
here instead of in `../SKILL.md`, which points here before Step 4e (sections 1–3) and
before Step 8 (all of it).

If `{ORG_BRANCHING_WORKFLOW}` exists, follow it, but it must honour every rule in section 1.
Where it does not, these rules win.

`../SKILL.md` Step 8's sub-steps map onto this file as: 8.1 → section 2, 8.2 → section 5,
8.3 → section 6, 8.4 → section 7, 8.5 → section 8 (8.6, merge order, stays in `../SKILL.md`).

---

## 1. Non-negotiable rules

**Rule 1: one version-catalogue branch per fix.** `{VERSION_CATALOGUE_REPO}` gets exactly one
branch, `{FIX_BRANCH_PREFIX}{feature-slug}`, chosen with `pick_branch` (section 3). The
primary module's bump is its first commit; every consumer's bump is another commit on the
**same** branch. Never one branch per consumer. Result: exactly one catalogue PR. On a re-run
for the same slug the existing branch is resumed, never forked.

**Rule 2: versions come from the tracker, never from source.** Read each module's current
version from `{VERSION_TRACKER_FILE}` on `{VERSION_TRACKER_BRANCH}`; increment; write it back;
commit; push `{VERSION_TRACKER_BRANCH}` immediately; only then apply the same version to
`{SHARED_VERSION_CATALOGUE}` on the fix branch. Never take the starting version from
`{SHARED_VERSION_CATALOGUE}` or from `{DEFAULT_BRANCH}`: those reflect the last *merged* bump,
so two concurrent runs would compute the same "next" version and the second merge would
silently overwrite the first. The tracker is a live ledger of *in-flight* versions. The one
exception is a version this fix already reserved (section 4): it is reused, not re-read.

**Rule 3: published version equals declared version.** For the primary module and every
library consumer, also bump the version in the module's **own** build file (the value its CI
publishes: a `version = "x.y.z"` string or a `versionPatch`-style integer). Verify the
composed version equals the version written to `{SHARED_VERSION_CATALOGUE}` (minus any suffix
such as `-SNAPSHOT`, if your scheme uses one only in the catalogue). If only the catalogue is
bumped, consumers ask for `x.y.(n+1)` while CI keeps publishing `x.y.n`, and resolution fails
for every consumer after merge. Application repos publish nothing; skip this rule for them.

**Rule 4: submodule pointer, if you use one.** If repos pin `{VERSION_CATALOGUE_REPO}` as a
submodule under `{SHARED_BUILD_CONFIG_DIR}`, the primary repo's fix branch gets a separate
commit moving that pointer to the catalogue branch's HEAD *after* the primary bump is
committed there; each consumer's fix branch does the same after its own bump. Re-resolve the
catalogue HEAD per repo, so each later repo captures every earlier bump. Without this, the
repo builds against the old catalogue and CI publishes the wrong version. If a repo is not
actually wired as a submodule, warn and leave it for a human to sync. If the pointer already
equals the catalogue HEAD (a resumed run), make no commit.

**Rule 5: one branch name everywhere.** Primary, catalogue, and every consumer repo use the
same `{FIX_BRANCH_PREFIX}{feature-slug}`, one PR each into `{DEFAULT_BRANCH}`. No other
prefixes, no intermediate or integration branches. The only exception is a repo where that
name is already taken by a branch this skill did **not** write for this issue (its head
commit has no `Issue: {issue_id}` trailer): that repo uses
`{FIX_BRANCH_PREFIX}{git_user}/{feature-slug}` instead, and the run logs why.

**Rule 6: consumers in order, one at a time, even with no code change.** Process
`$ORDERED_CONSUMERS` sequentially: library consumers first, `{BASE_APP_MODULES}` last. For
each: (a) stay on the same catalogue fix branch, (b) bump its version in the tracker and push
the tracker immediately, (c) bump it in `{SHARED_VERSION_CATALOGUE}` on the same catalogue
branch, (d) bump its own build file (libraries only), (e) move its submodule pointer (if
applicable). **(b)–(d) are mandatory even when the consumer has no source changes**: it must
republish so *its* consumers can resolve the new chain. A base app that publishes nothing and
has no row in `{VERSION_TRACKER_FILE}` gets only (e); if your org does track app versions
there, bump its row too. A consumer whose repo cannot be found is skipped entirely, not
bumped (section 8 step 1).

**Rule 7: the tracker is updated during the run, not at merge.** Push each module's new
version to `{VERSION_TRACKER_BRANCH}` as soon as it is computed, before that module's PR
exists. `{SHARED_VERSION_CATALOGUE}` reaches `{DEFAULT_BRANCH}` only when its PR merges; the
tracker is always current, so the next run increments from the right base.

**Every commit this skill makes carries the trailer `Issue: {issue_id}`** as its last line
(use `commit_skill`, section 2). The trailer is how a re-run tells its own earlier branches
and reservations apart from anyone else's (Rule 5, section 4).

---

## 2. Shared helpers

Shell state does not persist between separate tool calls. Re-declare these helpers and
re-derive variables in each command block rather than relying on an earlier `export`.

```bash
export GIT_EDITOR=true VISUAL=true EDITOR=true   # no interactive editors, ever
ISSUE_ID="{issue_id}"

# Portable in-place sed (usage: sedi EXPRESSION FILE). GNU sed takes -i alone;
# BSD/macOS sed needs an explicit (empty) backup suffix.
sedi() { if sed --version >/dev/null 2>&1; then sed -i "$1" "$2"; else sed -i '' "$1" "$2"; fi; }

# Commit with the skill's trailer (usage: commit_skill SUBJECT [BODY]).
commit_skill() { git commit -m "$1" ${2:+-m "$2"} -m "Issue: $ISSUE_ID"; }

# Retry pushes of a branch only this run writes to (usage: push_retry BRANCH).
# Transient network failures only; the shared tracker branch uses rebase-and-retry instead.
# Never --force: a resumed branch only ever gains commits.
push_retry() {
  local n=1 delay=2
  until git push -u origin "$1"; do
    [ "$n" -ge 3 ] && { echo "❌ FATAL: push of $1 failed after 3 attempts."; return 1; }
    echo "⚠️ WARN: push of $1 failed (attempt $n/3) — retrying in ${delay}s"; sleep "$delay"
    n=$((n + 1)); delay=$((delay * 2))
  done
}

# Strict version bump (usage: NEW=$(bump "$OLD") || fatal). Accepts only
# MAJOR.MINOR.PATCH with an optional -suffix; anything else prints INVALID and fails.
bump() {   # "1.4.9-SNAPSHOT" -> "1.4.10-SNAPSHOT"
  local v="$1" suffix="" core
  case "$v" in *-*) suffix="-${v#*-}"; core="${v%%-*}";; *) core="$v";; esac
  printf '%s\n' "$core" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "INVALID"; return 1; }
  case "$suffix" in ''|-[0-9A-Za-z.]*) ;; *) echo "INVALID"; return 1;; esac
  echo "${core%.*}.$(( 10#${core##*.} + 1 ))${suffix}"   # 10# so a patch like 08 is not octal
}

[ -n "$(git config user.email)" ] || { echo "❌ FATAL: git user.email is not set."; exit 1; }
GIT_USER=$(git config user.name | tr '[:upper:] ' '[:lower:]-' | tr -cd '[:alnum:]-' | head -c 20)
[ -n "$GIT_USER" ] || GIT_USER=$(hostname | tr '[:upper:].' '[:lower:]-' | head -c 15)
```

`bump` outputs, for reference: `1.4.9 → 1.4.10`, `1.4.9-SNAPSHOT → 1.4.10-SNAPSHOT`,
`10.0.99 → 10.0.100`; `1.4`, `7`, `1.4.9.2`, `abc`, `1.4.9-` → `INVALID`. If your scheme caps
components (e.g. patch rolls into minor at 99) or zero-pads them, apply that rule here
consistently. An `INVALID` result is `❌ FATAL`: never write a malformed version.

**Git-host credentials:** resolve a token without prompting: first an existing
`{GIT_HOST_CLI}` auth session, then a token in the environment (e.g. `GIT_HOST_TOKEN`) or git
config. If you have to log the CLI in from a token, persist the session in the CLI's own
config and then `unset` the variable: later steps run as separate shell invocations, and the
raw token should not linger in shell state. With no credential at all, the run can still
complete Steps 0–7; Step 8 then emits `❌ FATAL: No git-host credentials — branches cannot be
pushed.` and the run result records `status: "FATAL"` with everything produced so far.

Resolve `{catalogue_path}` (the local checkout of `{VERSION_CATALOGUE_REPO}`): workspace
config field → a directory of that name under `{workspace_root}` → the submodule directory
inside the primary repo. None → `❌ FATAL: {VERSION_CATALOGUE_REPO} not found under
{workspace_root}.` (only when consumers or a library bump are needed).

Resolve `{git_namespace}`: `GIT_NAMESPACE` → workspace config → parsed from the primary repo's
`origin` URL.

---

## 3. Repo sync and fix branch

Run this in every repo **before** reading its source for analysis (`../SKILL.md` Step 4e) and
before any edit: the primary repo at Step 4e, the catalogue repo at section 6, each consumer
at section 8. Analysing a stale or half-switched checkout is how "already fixed upstream"
gets missed and how a `pull` later aborts over local edits.

```bash
cd "{workspace_root}/{repo_name}" || exit 1
test -d .git || { echo "❌ FATAL: {repo_name} is not a git checkout."; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "❌ FATAL: {repo_name} has uncommitted changes — commit or stash them, then re-run."; exit 1; }
git fetch origin
git checkout "{DEFAULT_BRANCH}" && git pull --ff-only origin "{DEFAULT_BRANCH}" \
  || { echo "❌ FATAL: {repo_name}: cannot fast-forward {DEFAULT_BRANCH}."; exit 1; }

# Choose the branch: resume this issue's branch, or create it. Never a bare `checkout -b`,
# which fails when a local branch of that name survives from an earlier run.
pick_branch() {
  local cand rc
  for cand in "{FIX_BRANCH_PREFIX}{feature-slug}" "{FIX_BRANCH_PREFIX}$GIT_USER/{feature-slug}"; do
    git ls-remote --exit-code --heads origin "$cand" >/dev/null 2>&1; rc=$?
    case "$rc" in
      2) git checkout -B "$cand" "{DEFAULT_BRANCH}" || return 1         # new branch
         echo "ℹ️ AUTO: created $cand from {DEFAULT_BRANCH}"; BR="$cand"; return 0 ;;
      0) git fetch origin "$cand" || return 1
         if git log -1 --format=%B "origin/$cand" | grep -qxF "Issue: $ISSUE_ID"; then
           git checkout -B "$cand" "origin/$cand" || return 1           # resume an earlier run
           echo "ℹ️ AUTO: resuming $cand from an earlier run"; BR="$cand"; return 0
         fi
         echo "⚠️ WARN: $cand exists but was not written by this skill for $ISSUE_ID — not touching it." ;;
      *) echo "❌ FATAL: cannot query origin for $cand (exit $rc)."; return 1 ;;
    esac
  done
  echo "❌ FATAL: both branch names for {feature-slug} are taken by branches this skill did not write."; return 1
}
pick_branch || exit 1
```

- `git checkout -B` resets a leftover local branch to the chosen start point. Local commits
  that never reached the remote are discarded (they stay in the reflog); the run recreates
  them.
- A resumed branch is never rebased or force-pushed. If it has fallen behind
  `{DEFAULT_BRANCH}`, the PR shows that for a human.
- On a resumed branch the earlier run's fix may already be present. Analysis still reasons
  about the unfixed code: read `git diff "{DEFAULT_BRANCH}"...HEAD` to see what the earlier
  run changed, and read the pre-fix files with `git show "{DEFAULT_BRANCH}":{path}`.
- `ACTION=ANALYSE` never runs this section. It runs `git fetch origin` only and reads the
  chain's files with `git show origin/{DEFAULT_BRANCH}:{path}` when the checkout is not a
  clean, current `{DEFAULT_BRANCH}` (`../SKILL.md` Step 4e).

---

## 4. What a re-run reuses

The feature slug is the idempotency key. Everything a re-run reuses is found on the git
host, never in local memory or a prior run's files (Guardrails 2–4).

| Already on the git host | A re-run does |
|---|---|
| `{FIX_BRANCH_PREFIX}{feature-slug}` whose head carries `Issue: {issue_id}` | `git checkout -B "$BR" "origin/$BR"` and continues on it |
| Same name, head without that trailer (someone else's branch) | Uses `{FIX_BRANCH_PREFIX}{git_user}/{feature-slug}` (resumed the same way if it exists) |
| A `chore: bump {module} to {v}` commit on the catalogue fix branch | Reuses `{v}`; no tracker increment, no second catalogue commit |
| A tracker commit `chore: {module} → {v}` with trailer `Issue: {issue_id}`, but no catalogue commit (a run that failed between section 6 steps 6 and 7), and `{v}` not yet on `{DEFAULT_BRANCH}` | Reuses `{v}`; no tracker increment; makes the missing catalogue commit |
| A `chore: bump {module} version to …` commit on the module's own fix branch | Skips the own-build-file bump |
| Submodule pointer already equal to the catalogue branch HEAD | No pointer commit |
| An open PR whose source branch is exactly `$BR` | Reuses its URL (`reused_existing: true`) |

Find a reserved version (run in `{catalogue_path}` after section 3 picked `$BR`):

```bash
reserved_version() {   # usage: reserved_version MODULE  -> prints the version or nothing
  local m="$1" v
  v=$(git log "origin/{DEFAULT_BRANCH}..origin/$BR" --format=%s 2>/dev/null \
        | sed -n "s/^chore: bump $m to \(.*\)$/\1/p" | head -1)
  if [ -z "$v" ]; then
    v=$(git log "origin/{VERSION_TRACKER_BRANCH}" -F --grep="Issue: $ISSUE_ID" --format=%s \
          | sed -n "s/^chore: $m → \(.*\)$/\1/p" | head -1)
    # A reservation that already merged belongs to an earlier, released fix: bump afresh.
    [ -n "$v" ] && git show "origin/{DEFAULT_BRANCH}:{SHARED_VERSION_CATALOGUE}" | grep -qF "\"$v\"" && v=""
  fi
  printf '%s' "$v"
}
```

Log every reuse as `ℹ️ AUTO: {module} already bumped to {v} on this fix branch — reusing`
and record it in the run result with `"reused_existing": true` in `versions[]`.

---

## 5. Primary repo: commit the fix

`ACTION=FIX` only. The branch was picked in section 3 at Step 4e and the Step 7 edits are
already on it. This step only stages, commits, and pushes.

Stage exactly the paths in `sprint_plan.json tasks[].files[].path` plus the test files you
created (never `git add -A`). If the staged diff is empty because a resumed branch already
holds this fix, emit `ℹ️ AUTO: fix already committed on $BR — no new commit` and skip the
commit. Otherwise:

```bash
commit_skill "fix({simple_name}): {title}" "Type: {ISSUE_TYPE}
Impact: {impact_summary}"
push_retry "$BR"
```

If no paths resolved at all, `⚠️ WARN: no fix files found to commit — the PR will need the
fix committed manually.`

---

## 6. Library modules: version bump

Skip if the primary module is an application. Otherwise, in `{catalogue_path}`:

1. **Catalogue branch (Rule 1).** Run section 3 in the catalogue repo: sync, then
   `pick_branch`. If the branch is new, push it (`push_retry "$BR"`).
2. **Reserved version? (section 4).** `V=$(reserved_version {primary_module})`. If non-empty,
   set `{new_version}` = `$V`, log the reuse, and skip the tracker increment (steps 3–6).
   If the catalogue fix branch already has the bump commit, also skip step 7's edit and
   commit (still run its key-line verification); otherwise do step 7 in full.
3. **Read from the tracker (Rule 2).** `git fetch origin {VERSION_TRACKER_BRANCH} && git
   checkout {VERSION_TRACKER_BRANCH} && git pull --ff-only`. Find the primary module's row
   in `{VERSION_TRACKER_FILE}` (format: `../SKILL.md` Configuration). No row →
   `❌ FATAL: {primary_module} has no entry in {VERSION_TRACKER_FILE} — add one and re-run.`
4. **Increment.** `NEW=$(bump "$OLD") || { echo "❌ FATAL: {primary_module} version '$OLD'
   is not MAJOR.MINOR.PATCH."; exit 1; }` (helper in section 2).
5. **Collision guard.** If `{new_version}` already appears on this module's line in
   `{SHARED_VERSION_CATALOGUE}` on `origin/{DEFAULT_BRANCH}` (or your release branch), the
   tracker is stale: `❌ FATAL: {new_version} is already on {DEFAULT_BRANCH} — the tracker
   is behind; correct it and re-run.`
6. **Write and push the tracker immediately (Rule 7).** Replace the version and
   `updated_by` (= `$GIT_USER`) in that row only; `commit_skill "chore: {primary_module} →
   {new_version}"`; push. If the push is rejected because another run moved the branch,
   `git fetch` + `git rebase origin/{VERSION_TRACKER_BRANCH}` and push once more; if the
   rebase conflicts on the same row, `git rebase --abort` and
   `❌ FATAL: concurrent bump of {primary_module} — re-run so the version is re-read.`
7. **Apply to the catalogue.** `git checkout "$BR"`; replace the module's version in
   `{SHARED_VERSION_CATALOGUE}` with the new one (`sedi` on the module's own key line only).
   **Verify the module's own key line** now holds the new value, not just that the value
   appears somewhere: another module may already be at the same version, so a whole-file
   `grep -F` passes after a no-op `sed`. With `{catalogue_key}` from Step 4h pass 2 and
   `NV="${NEW//./\\.}"`:
   - TOML catalogue: `grep -qE "^[[:space:]]*{catalogue_key}[[:space:]]*=[[:space:]]*\"$NV\"" {SHARED_VERSION_CATALOGUE}`
   - `Versions.kt` object: `grep -qE "const val {catalogue_key}[[:space:]]*=[[:space:]]*\"$NV\"" {SHARED_VERSION_CATALOGUE}`

   No match → `❌ FATAL: {SHARED_VERSION_CATALOGUE} line for {catalogue_key} does not hold
   {new_version}.` Then `commit_skill "chore: bump {primary_module} to {new_version}"`;
   `push_retry "$BR"`.
8. **Bump the module's own build file (Rule 3)** on the primary repo's fix branch: either the
   literal `version = "…"` or the patch integer, whichever the file uses. Skip when a
   `chore: bump {module} version to …` commit is already on that branch. Neither found →
   `❌ FATAL: no version declaration in {build_file}.` Verify composed version = catalogue
   version (minus suffix). `commit_skill "chore: bump {module} version to {bare_version}"`;
   push.
9. **Compile again.** Re-run the module compile from Step 7 against the bumped configuration.
   If the bump itself breaks the build: the tracker already holds `{new_version}`, so add
   `tracker ahead: {primary_module} {new_version} has no PR` to `run_result.warnings`, then
   `❌ FATAL: version bump broke the {primary_module} build.` Never raise a PR whose failure
   you introduced in this step. (A compile failure carried over from Step 7 is already
   recorded in `{test_status}`; do not re-litigate it here.)
10. **Submodule pointer (Rule 4)** on the primary repo's fix branch, as its own commit:
    `commit_skill "chore: point {SHARED_BUILD_CONFIG_DIR} to {sha} ({primary_module} {new_version})"`.

---

## 7. Primary PR, then catalogue PR

Before creating any PR, look for an open one with the same source branch (`$BR`, exactly) in
that repo (`{GIT_HOST_CLI}` list, filtered by source branch and state open). If found, reuse
its URL (`ℹ️ AUTO: PR already open → {url}`) and update its description instead of opening a
duplicate. Because a re-run resumes the same branch (section 3), this check matches the
earlier run's PR.

Primary PR: title `[{ISSUE_TYPE}] {title}`, body from `crash_doc_template.md` → "Pull/merge
request description", into `{DEFAULT_BRANCH}`, with `{MR_LABELS}` if configured.

Catalogue PR (only if section 6 ran): title `chore: bump {primary_module} to {new_version}`
(it will accumulate consumer bumps; update its description at the end of section 8 to list
them all), body listing every module bump `old → new`, the fix slug, the issue link, and the
instruction to merge it **first**.

---

## 8. Each consumer

For each consumer in `$ORDERED_CONSUMERS`, sequentially (Rule 6):

1. **Null-path guard.** Its repo must be on disk; else try the Step 4g clone. Still missing →
   `⚠️ WARN: {consumer} repo not found — not bumped, PR not raised; follow up manually.`
   Record it in `consumers.skipped` and go to the next consumer (one missing repo never
   aborts the cascade). It is not bumped, because a version that no PR will ever publish
   would break resolution for its own consumers.
2. **Sync and branch** (section 3) in the consumer repo.
3. **Version** for this consumer: `reserved_version` first (section 4), else tracker bump +
   push (section 6 steps 3–6).
4. Catalogue bump on the **same** catalogue fix branch (section 6 step 7), unless reused.
5. Own build-file bump (section 6 step 8), **libraries only**. Determine "application" by
   `{BASE_APP_MODULES}` membership or `com.android.application` in its build files. Use the
   `build_file` recorded in Step 4h as the first candidate path.
6. Compile the consumer module (compile-only task).
7. Submodule pointer → the catalogue branch's *current* HEAD (Rule 4).
8. Push (`push_retry "$BR"`) and raise or reuse its PR (section 7's reuse check) with the
   same description template, adding a **Module bumped** row (`{primary_module} {old} →
   {new}`) and merge instructions naming the catalogue PR URL.

**Mid-cascade failure guard.** The tracker is pushed before each consumer's PR exists. If a
step after the tracker push fails for a consumer (push, PR creation, permissions, network,
conflict), stop the remaining cascade, add `tracker ahead: {consumer} {new_version} has no
PR` to `run_result.warnings`, set `status: "PARTIAL"`, and emit:

```
⚠️ WARN: {consumer} was bumped in the tracker but its PR could not be raised — the tracker
         is ahead of the raised PRs. Re-run with the same inputs to finish (section 9).
```

If **every** consumer was skipped for a missing repo, say so loudly in the summary: the
primary PR is still valid, but no downstream module will pick up the fix.

---

## 9. Failure recovery: tracker ahead of PRs

A `tracker ahead: {module} {version} has no PR` warning means `{VERSION_TRACKER_BRANCH}`
reserved a version that no open PR uses yet. To reconcile:

1. **Re-run the skill with the same inputs.** The slug is the same, so the run resumes the
   same branches, finds the reservation (the catalogue commit, or the tracker commit carrying
   `Issue: {issue_id}`), reuses that version without a second increment, and raises the
   missing PRs. This is the normal recovery.
2. **If the cause was a build broken by the bump** (section 6 step 9), fix the build on the
   fix branch by hand, then re-run, or raise that module's PR by hand using the reserved
   version.
3. **If the fix is abandoned**, close its PRs and leave the tracker as it is. A skipped
   version number is harmless. Never decrement a tracker row: another run may already have
   read it and bumped from it.
