# Consumer detection (Step 4h)

**Contents:** [Why this file exists](#why-this-file-exists) · [Scan root and candidates](#scan-root-and-candidates) ·
[Detection passes](#detection-passes) · [When detection fails](#when-detection-fails) ·
[Direct vs transitive](#direct-vs-transitive) · [Ordering and output](#ordering-and-output)

## Why this file exists

When the primary module is a library, every repo that depends on it directly needs a
version bump and its own PR, or it stays pinned to the old artifact and never ships the fix.
A false *empty* consumer list fails silently: no error, just a fix that never reaches users.
These passes are how `../SKILL.md` Step 4h finds consumers reliably. They run on every
invocation, always fresh from disk, in both `ACTION=FIX` and `ACTION=ANALYSE` (in ANALYSE the
list only informs the blast radius in the document).

Never take the consumer list from memory or a previous `sprint_plan.json`; never skip this
because PRs already exist. Skip only when the primary module is an application.

---

## Scan root and candidates

**Scan root.** First existing directory of: `WORKSPACE_ROOT`, the workspace config's
directory, `{workspace_root}`. If none: `⚠️ WARN: No scan root — consumer detection skipped.`

**Exclude the primary repo** from every pass. A module is never its own consumer.

**Scan every repo** listed under both `modules{}` and `apps{}` in the workspace config (they
are peers; skipping `apps{}` silently drops the base apps), or every repo directory under the
scan root when there is no config.

If `{ORG_CONSUMER_DETECTION}` exists, **source** it (do not run it as a subprocess: its
output variables must land in the calling shell) with `SCAN_ROOT`, `PRIMARY_REPO_NAME`,
`PRIMARY_MODULE`, `PRIMARY_NAMESPACE` exported. Otherwise run the passes below inline.

---

## Detection passes

- **Pass 1: artifact coordinate.** Grep `build.gradle*` / `*.toml` in each candidate repo
  for the primary module's `group:artifact` coordinate. Resolve the repo list into a
  variable first; never inline a subshell into `grep`'s arguments, where a silent failure
  yields zero paths and no warning. Exclude `build/` and `.git/`.
- **Pass 2: catalogue alias / constant.** Look up the alias or constant that
  `{SHARED_VERSION_CATALOGUE}` declares for the coordinate (e.g. `libs.example.orders` or
  `Deps.ordersLib`) and grep candidate build files for it. This catches repos that consume the
  catalogue as an uninitialised submodule, whose build files never mention the raw
  coordinate. Record the version key the catalogue uses for the primary module and for each
  consumer as `catalogue_key`; the cascade's key-line verification needs it
  (`version_cascade.md` section 6 step 7).
- **Pass 3: aggregate lists.** Some base apps include every internal module through one
  bundle or array declared in the catalogue. Detect repos that reference the bundle, and
  confirm the primary module's alias is actually a member of it.
- **Pass 4: false-positive elimination (mandatory).** For every candidate, log the exact
  file and line that matched. Discard any match that sits inside the shared catalogue's own
  directory, is only a declaration (not a use), or is not inside an `implementation` /
  `api` / `compileOnly` / `runtimeOnly` (or bundle) context.

---

## When detection fails

**No improvised searching.** If detection fails (missing parser, unreadable config, script
exits non-zero), do not fall back to grepping the shared catalogue for the module name: the
catalogue *declares* every module for everyone, so a hit there proves nothing. Emit:

```
⚠️ WARN: Consumer detection failed — continuing with zero consumers.
         Only the primary module PR will be raised; consumer bumps SKIPPED.
         Fix: {the specific cause} and re-run.
```

and record the warning in the run result.

If the result is empty for a library that the catalog or config says is widely used, emit
`⚠️ WARN: zero consumers detected for {primary_module} — verify; a false empty leaves every
real consumer pinned to the old artifact.`

---

## Direct vs transitive

Only **direct** consumers (an explicit dependency on the primary coordinate) are bumped. If
`A → B → C` and C is the primary module, B is bumped; A picks up C transitively when B
republishes. Bump A as well only if the fix changes a public API that A calls directly *and*
B does not re-export it.

---

## Ordering and output

Build `$ORDERED_CONSUMERS`: library consumers first (sorted so that a library appears after
any other library consumer it depends on), `{BASE_APP_MODULES}` last, always. Base apps last
means their single catalogue-pointer commit captures every bump in the cascade.

Emit one line per consumer:

```
ℹ️ AUTO: Consumer → {consumer_module} in {consumer_repo}
         matched: {build_file}:{line}  "{matching line}"
```

or `ℹ️ AUTO: No consumers detected for {primary_module} — leaf library or not yet published.`

Record each as `{ "module", "repo_name", "build_file", "catalogue_key", "is_app" }` in
`sprint_plan.json._meta.consumer_modules`, in iteration order, and the primary module's key
as `_meta.primary_catalogue_key`.
