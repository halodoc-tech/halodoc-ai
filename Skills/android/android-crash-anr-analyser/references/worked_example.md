# Worked example (fictional, abbreviated)

**Contents:** [Why this file exists](#why-this-file-exists) · [Input](#input) ·
[Walkthrough](#walkthrough) · [Tracker file sample](#tracker-file-sample) ·
[Final run result](#final-run-result-abridged) · [Re-run of the same issue](#re-run-of-the-same-issue) ·
[What to check in a real run](#what-to-check-in-a-real-run)

## Why this file exists

The cascade rules in `version_cascade.md` are easy to read and still hard to picture: how many
pull/merge requests one ANR produces, in which repos, in what order, what a re-run does, and
what the final run result looks like. This walkthrough makes that shape concrete so a real run
can be checked against it. Every name, ID, count, and version below is invented;
`{PLACEHOLDERS}` stand for your own Configuration values.

---

## Input

A CI job (the `CI` variable is set), so `ACTION` defaults to `FIX`:

```
ISSUE_TYPE=ANR  APP=SHOP  ISSUE_RANK=1
```

## Walkthrough

1. **Step 0** — `mode=A action=FIX issue_type=ANR app=SHOP issue_rank=1`
   (`ℹ️ AUTO: action=FIX (rule 2)`).
2. **Step 1** — `workspace_root` from the workspace config failed `test -d` (a developer's
   laptop path), so the CI workspace variable was used. `⚠️ WARN` logged.
3. **Step 2** — `SHOP` resolves through `{APP_REGISTRY}` to "Example Shop - Android". Top ANR
   issues fetched; rank 1 is *"Input dispatching timed out — HomeFeedFragment"*.
4. **Step 3** — three sample events. Every one shows `main` in state `BLOCKED`,
   `waiting to lock <0x0a1b>` inside `FeedCache.snapshot()`. Thread `feed-sync-2` shows
   `- locked <0x0a1b>` in `FeedCache.refresh()`, itself inside a `FileInputStream.read`.
5. **Step 4a** — the blocking frame is `FeedCache.snapshot()` on main; the lock holder is
   `feed-sync-2` in `FeedCache.refresh()`, which holds the cache monitor across a disk read.
   Root location = `FeedCache.refresh()`.
6. **Step 4c** — **C6-LOCK** (main waits on a lock held across I/O).
7. **Step 4g** — frame class `com.example.shop.catalogue.FeedCache` (no `$`, no `Kt`) →
   `com.example.shop.catalogue` → `catalogue-lib` from the module catalog; cloned because it
   was not on disk.
8. **Step 4e** — slug `anr-fix-feedcache-7d20b8e4a6c1`. Sync `catalogue-lib`: tree clean,
   fetch, `{DEFAULT_BRANCH}` fast-forwarded; `pick_branch` finds no remote branch →
   `ℹ️ AUTO: created {FIX_BRANCH_PREFIX}anr-fix-feedcache-7d20b8e4a6c1 from {DEFAULT_BRANCH}`.
   After reading `FeedCache`, `HomeFeedViewModel`, and `FeedSyncWorker`:
   > "`FeedCache.snapshot()` blocks the main thread because `FeedCache.refresh()` holds the
   > cache monitor for the full duration of a disk read when a background sync overlaps the
   > home screen opening."

   Validation: explains why main blocks in `snapshot()` (it needs the same monitor); the
   volume fits (only when a sync overlaps a cold open); signal *regressed* lines up with the
   version that moved the cache to disk; all three samples agree. Confidence `HIGH`.
9. **Step 4f** — root-cause fix: read the file *outside* the lock and swap the parsed result
   in under a short critical section; have the ViewModel read the snapshot on
   `Dispatchers.IO`. No symptom guard needed.
10. **Step 4h** — consumers: `orders-lib` (Pass 2: catalogue alias in its build file) and
    `example-shop-app` (Pass 3: aggregate bundle). Ordered: `orders-lib`, then
    `example-shop-app`.
11. **Steps 5–6** — analysis document, `sprint_plan.json` (one task), `test_cases.json`.
    TC-001: a fake slow reader holds the lock inside `refresh()` on a background thread; the
    test calls `snapshot()` and asserts it returns within 200 ms. TC-003: a normal refresh
    still updates the snapshot.
12. **Step 7** — TC-001 written first and run against the unfixed code: it **failed** with
    `AssertionError: snapshot() still blocked after 200 ms` (the hypothesised lock wait), so
    `reproduction_verified = true`. Fix applied; TC-002/TC-003 written. Compile failed once
    (missing import), fixed on attempt 2. Unit tests pass, TC-001 included.
    `test_status = "PASSED"`.
13. **Step 8** — all on branch `{FIX_BRANCH_PREFIX}anr-fix-feedcache-7d20b8e4a6c1`, every
    commit ending in `Issue: 7d20b8e4a6c1`:
    - `catalogue-lib`: fix commit pushed; tracker `catalogue-lib 3.2.7 → 3.2.8` pushed;
      catalogue bumped on the one catalogue branch (key line `catalogue-lib = "3.2.8"`
      verified); own build file `versionPatch 7 → 8`; submodule pointer commit; PR raised.
    - catalogue repo: PR raised (later updated to list both bumps).
    - `orders-lib` (no code change): synced, branch created; tracker `2.9.4 → 2.9.5`;
      catalogue commit on the same branch; own build file bumped; pointer commit; PR raised.
    - `example-shop-app` (base app, publishes nothing): pointer commit only; PR raised.
14. **Step 9** — summary printed, then the run result.

## Tracker file sample

`{VERSION_TRACKER_FILE}` on `{VERSION_TRACKER_BRANCH}` after this run. One row per publishable
module, `module` spelled exactly as the module name the skill resolves, `version` strictly
`MAJOR.MINOR.PATCH[-suffix]`:

```markdown
| module | version | updated_by |
|---|---|---|
| catalogue-lib | 3.2.8 | ci-runner |
| orders-lib | 2.9.5 | ci-runner |
| core-kit | 5.14.2 | ci-runner |
```

The two tracker commits this run made are `chore: catalogue-lib → 3.2.8` and
`chore: orders-lib → 2.9.5`, each ending in `Issue: 7d20b8e4a6c1`.

## Final run result (abridged)

```json
{
  "skill": "android-crash-anr-analyser",
  "status": "SUCCESS",
  "mode": "A",
  "action": "FIX",
  "analysis": {
    "issue_class": "C6-LOCK",
    "origin": "APP",
    "root_location": "com.example.shop.catalogue.FeedCache.refresh:88",
    "confidence": "HIGH",
    "symptom_guard_used": false,
    "regression_risk": "MEDIUM",
    "release_verdict": "SAFE TO RELEASE"
  },
  "build": { "compile_status": "PASSED", "compile_attempts": 2, "test_status": "PASSED", "reproduction_verified": true },
  "versions": [
    { "module": "catalogue-lib", "from": "3.2.7", "to": "3.2.8", "tracker_pushed": true, "reused_existing": false },
    { "module": "orders-lib", "from": "2.9.4", "to": "2.9.5", "tracker_pushed": true, "reused_existing": false }
  ],
  "pull_requests": [
    { "merge_order": 1, "role": "catalogue", "repo": "{VERSION_CATALOGUE_REPO}", "reused_existing": false },
    { "merge_order": 2, "role": "primary", "repo": "catalogue-lib", "reused_existing": false },
    { "merge_order": 3, "role": "consumer", "repo": "orders-lib", "reused_existing": false },
    { "merge_order": 4, "role": "base_app", "repo": "example-shop-app", "reused_existing": false }
  ],
  "fatal": null
}
```

## Re-run of the same issue

Suppose the first run had stopped after the `orders-lib` tracker push because PR creation
failed (`status: "PARTIAL"`, warning `tracker ahead: orders-lib 2.9.5 has no PR`), and CI runs
the same inputs again the next day:

- Same issue → same slug `anr-fix-feedcache-7d20b8e4a6c1` → same output directory (artifacts
  overwritten) and the same branch names. The analysis itself is redone from scratch.
- `catalogue-lib`, catalogue repo, `orders-lib`: each remote branch exists and its head ends in
  `Issue: 7d20b8e4a6c1`, so `pick_branch` resumes it with
  `git checkout -B "$BR" "origin/$BR"`. No `{git_user}/` branch is created.
- `catalogue-lib` version: the catalogue branch already has `chore: bump catalogue-lib to
  3.2.8` → `ℹ️ AUTO: catalogue-lib already bumped to 3.2.8 on this fix branch — reusing`. No
  tracker commit; the tracker stays at `3.2.8`.
- The primary fix is already on its branch → `ℹ️ AUTO: fix already committed on $BR — no new
  commit`. TC-001 is still re-verified against the unfixed files from `{DEFAULT_BRANCH}`.
- `orders-lib`: the catalogue commit exists, so `2.9.5` is reused; the PR is now raised.
- Primary and catalogue PRs: an open PR already exists for each exact branch → URLs reused
  (`reused_existing: true`), descriptions updated.

Result: `status: "SUCCESS"`, the same four PRs, and the tracker still reads `3.2.8` / `2.9.5`.
One fix consumed one version per module.

## What to check in a real run

- **One branch name in every repo.** Different names for the same fix mean Rule 1 or Rule 5
  was broken, unless the log shows `⚠️ WARN: … exists but was not written by this skill`
  for that repo (a foreign branch held the name, so the `{git_user}/` form was used there).
- **One catalogue PR**, listed first, carrying every bump as separate commits.
- **Every commit ends in `Issue: {issue_id}`.** Without the trailer, the next re-run cannot
  recognise its own branches.
- **A consumer with no code change still got a tracker bump, a catalogue bump, and an
  own-build-file bump.** Missing ones leave its own consumers pinned to the old chain.
- **Base apps last**, and with no own-version bump.
- **TC-001 was seen to fail on the old code** (`reproduction_verified: true`). A reproduction
  test that passes either way proves nothing.
- **A re-run raised no new versions and no duplicate PRs.**
- **Nothing merged.**
