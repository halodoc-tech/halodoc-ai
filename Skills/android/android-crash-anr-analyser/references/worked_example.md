# Worked example (fictional, abbreviated)

## Why this file exists

The rules in `../SKILL.md` Step 8 are easy to read and still hard to picture: how many
pull/merge requests one ANR produces, in which repos, in what order, and what the final run
result looks like. This walkthrough makes that shape concrete so a real run can be checked
against it. Every name, ID, count, and version below is invented; `{PLACEHOLDERS}` stand
for your own Configuration values.

---

## Input

```
ISSUE_TYPE=ANR  APP=SHOP  ISSUE_RANK=1
```

## Walkthrough

1. **Step 0** — `mode=A issue_type=ANR app=SHOP issue_rank=1`.
2. **Step 1** — `workspace_root` from the workspace config failed `test -d` (a developer's
   laptop path), so the CI workspace variable was used. `⚠️ WARN` logged.
3. **Step 2** — `SHOP` resolves through `{APP_REGISTRY}` to "Example Shop - Android". Top
   ANR issues fetched; rank 1 is *"Input dispatching timed out — HomeFeedFragment"*.
4. **Step 3** — three sample events. Every one shows `main` in state `BLOCKED`,
   `waiting to lock <0x0a1b>` inside `FeedCache.snapshot()`. Thread `feed-sync-2` shows
   `- locked <0x0a1b>` in `FeedCache.refresh()`, itself inside a `FileInputStream.read`.
5. **Step 4a** — the blocking frame is `FeedCache.snapshot()` on main; the lock holder is
   `feed-sync-2` in `FeedCache.refresh()`, which holds the cache monitor across a disk
   read. Root location = `FeedCache.refresh()`.
6. **Step 4c** — **C6-LOCK** (main waits on a lock held across I/O).
7. **Step 4e** — after reading `FeedCache`, `HomeFeedViewModel`, and `FeedSyncWorker`:
   > "`FeedCache.snapshot()` blocks the main thread because `FeedCache.refresh()` holds the
   > cache monitor for the full duration of a disk read when a background sync overlaps
   > the home screen opening."

   Validation: explains why main blocks in `snapshot()` (it needs the same monitor); the
   volume fits (only when a sync overlaps a cold open); signal *regressed* lines up with
   the version that moved the cache to disk; all three samples agree. Confidence `HIGH`.
8. **Step 4f** — root-cause fix: read the file *outside* the lock and swap the parsed
   result in under a short critical section; have the ViewModel read the snapshot on
   `Dispatchers.IO`. No symptom guard needed.
9. **Step 4g/4h** — `com.example.shop.catalogue` → `catalogue-lib` (from the module catalog;
   cloned because it was not on disk). Consumers: `orders-lib` (Pass 2 — catalogue alias
   in its build file) and `example-shop-app` (Pass 3 — aggregate bundle). Ordered:
   `orders-lib`, then `example-shop-app`.
10. **Steps 5–6** — analysis document, `sprint_plan.json` (one task), `test_cases.json`:
    TC-001 holds the lock in a fake slow reader under `StandardTestDispatcher` and asserts
    `snapshot()` returns without waiting; TC-003 asserts a normal refresh still updates
    the snapshot.
11. **Step 7** — compile failed once (missing import), fixed on attempt 2. Unit tests pass.
    `test_status = "PASSED"`.
12. **Step 8** — all on branch `{FIX_BRANCH_PREFIX}anr-fix-feedcache-7d20b8e4a6c1`:
    - `catalogue-lib`: fix commit; tracker `catalogue-lib 3.2.7 → 3.2.8` pushed; catalogue
      bumped on the one catalogue branch; own build file `versionPatch 7 → 8`;
      submodule pointer commit; PR raised.
    - catalogue repo: PR raised (later updated to list all three bumps).
    - `orders-lib` (no code change): tracker `2.9.4 → 2.9.5`; catalogue commit on the same
      branch; own build file bumped; pointer commit; PR raised.
    - `example-shop-app` (base app, publishes nothing): pointer commit only; PR raised.
13. **Step 9** — summary printed, then the run result.

## Final run result (abridged)

```json
{
  "skill": "android-crash-anr-analyser",
  "status": "SUCCESS",
  "mode": "A",
  "analysis": {
    "issue_class": "C6-LOCK",
    "origin": "APP",
    "confidence": "HIGH",
    "symptom_guard_used": false,
    "regression_risk": "MEDIUM",
    "release_verdict": "SAFE TO RELEASE"
  },
  "build": { "compile_status": "PASSED", "compile_attempts": 2, "test_status": "PASSED" },
  "versions": [
    { "module": "catalogue-lib", "from": "3.2.7", "to": "3.2.8", "tracker_pushed": true },
    { "module": "orders-lib", "from": "2.9.4", "to": "2.9.5", "tracker_pushed": true }
  ],
  "pull_requests": [
    { "merge_order": 1, "role": "catalogue", "repo": "{VERSION_CATALOGUE_REPO}" },
    { "merge_order": 2, "role": "primary", "repo": "catalogue-lib" },
    { "merge_order": 3, "role": "consumer", "repo": "orders-lib" },
    { "merge_order": 4, "role": "base_app", "repo": "example-shop-app" }
  ],
  "fatal": null
}
```

## What to check in a real run

- **One branch name in every repo.** Different names for the same fix mean Rule 1 or
  Rule 5 was broken.
- **One catalogue PR**, listed first, carrying every bump as separate commits.
- **A consumer with no code change still got a tracker bump, a catalogue bump, and an
  own-build-file bump.** Missing ones leave its own consumers pinned to the old chain.
- **Base apps last**, and with no own-version bump.
- **TC-001 would fail on the old code.** A reproduction test that passes either way proves
  nothing.
- **Nothing merged.**
