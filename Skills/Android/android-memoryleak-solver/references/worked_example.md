# Worked example (abbreviated) — TEMPLATE

## Why this file exists

`../SKILL.md`'s Step 9c raises a whole cascade of pull/merge requests for a single leak —
the fix itself, a shared-version-catalogue bump, and a bump in every consumer module. It's
easy to read the *rules* in Step 9 and still not picture the *shape* of what a real run
produces: how many PRs, in what order, touching which repos, and why. This file exists to
make that shape concrete with one end-to-end trace, so a reader can sanity-check a real run
against it ("does this look like what Step 9 is supposed to produce?") without re-deriving
it from the rules each time.

**Use this for shape and sequencing only.** The ticket ID, class names, module names, and
consumer set below are all invented for illustration — every real run's actual root cause,
fix, and consumer set will differ. Wherever you see a `{PLACEHOLDER}`, substitute your own
organization's actual value (see the Configuration section of `../SKILL.md`).

---

## Example walkthrough

Input: an issue-tracker URL for `{ISSUE_TRACKER_PROJECT_KEY}-4603` (Tracker tickets mode).

1. **Step 3a** — fetch `{ISSUE_TRACKER_PROJECT_KEY}-4603`; title matches `{LEAK_TICKET_LABEL}`;
   trace extracted.
2. **Step 4** — the leaked object (`CheckoutLayout`) and reference chain include frames
   under `{FIRST_PARTY_PACKAGE_PREFIXES}payments...` → **app leak**. Module resolves to
   `example-payments` (repo `example-payments`, per the module catalog template).
3. **Step 5** — root cause: a Fragment registers its own Toolbar as the host Activity's
   support action bar and never detaches it in `onDestroyView()`, so the Activity's
   `AppCompatDelegate` keeps the Fragment's destroyed view subtree alive.
4. **Step 6** — `Android_mem_leaks.md` generated with the leak's summary, chain, root cause,
   repro steps, and fix approach.
5. **Step 8** — `example-payments` is a library → consumer detection finds two direct
   consumers, `example-checkout-flow` and `example-subscriptions`, plus
   `example-consumer-app` (a `{BASE_APP_MODULES}` entry, pre-seeded as the final consumer).
6. **Step 9** — fix applied and committed to `example-payments`'s
   `{FIX_BRANCH_PREFIX}memory_leak-{ISSUE_TRACKER_PROJECT_KEY}-4603` branch; `{build_command}`
   / `{test_command}` pass; pull/merge request raised. The shared version-catalogue repo
   bumps `example-payments`'s version on its own
   `{FIX_BRANCH_PREFIX}memory_leak-{ISSUE_TRACKER_PROJECT_KEY}-4603` branch and PR. Each
   consumer bumps its own version and (if applicable) its shared-build-config pointer on its
   own same-named branch and PR.
7. **Result** — 4 pull/merge requests raised (`example-payments`, the shared
   version-catalogue repo, `example-checkout-flow`, `example-subscriptions`), plus
   `example-consumer-app`'s version-bump PR. Reviewer merge order: the version-catalogue PR
   first, then `example-payments`, then each consumer.

---

## What to look for when comparing a real run to this

- **Exactly one branch name reused across every repo touched** (`{FIX_BRANCH_PREFIX}{feature-slug}`)
  — if you see different branch names in different repos for the same leak, Rule 1 or Rule 4
  in Step 9 was violated.
- **The version-catalogue PR is separate from the primary module's PR**, and is listed first
  in the merge order — never merged.
- **Every consumer got a version bump PR, even ones with zero code changes** — a consumer
  silently missing from the cascade is the failure mode Step 8b's "zero consumers" warning
  and Step 9b's null-path guards exist to catch.
