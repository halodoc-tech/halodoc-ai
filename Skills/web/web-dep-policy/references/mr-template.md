# Onboarding MR template

Title: `feat: onboard to the central dependency version policy (pnpm 10 config dependency)`

```markdown
## Dependency-governance — onboard <repo-name>

Onboards this repo to the centrally-governed dependency policy
(`@your-org/pnpm-plugin-dep-version-policy <version>`, published from the
`your-org/dependency-version-policy` repo's release pipeline). Commits are deliberately layered:

1. **`chore: convert pnpm-lock.yaml to lockfileVersion 9.0`** *(only for pnpm-8
   repos)* — pure format conversion via pnpm 9 with **zero resolution changes**
   (verified by diffing the resolved name@version set against master).
2. **`feat: onboard to the central dependency version policy`**
   - `packageManager: pnpm@10.34.5` (exact toolchain; CI provisioning derives
     from it) + `engines.pnpm >=10.4.0` (configDependencies feature floor)
   - `pnpm-workspace.yaml` registers the policy config dependency (exact
     version + sha512; pnpm verifies the hash on every install)
   - Governed deps become `catalog:` pointers:
     | dep | before | after | bump |
     |---|---|---|---|
     | <dep> | <old> | <policy> | patch/minor/**major** |
   - **Deferred:** none possible — the local-pin guard fails the install for any
     governed dep left on a literal version, so every governed dep a repo declares
     converts together. If one had to diverge, say which `exceptionCatalogs` entry
     covers it and link the policy MR.
   - Lockfile delta: catalogs snapshot + `pnpmfileChecksum` + the governed
     bumps above. <If applicable:> pnpm 10's peer resolution also drops
     orphaned duplicate subtrees (removals only — no other version changes.>

### Evidence — build #N green
```
provisioning pnpm@10.34.5 (from package.json packageManager)
pinned: <ver> | latest: <…> | rc: <…>
PASS: policy pin valid for its channel, integrity verified.
injected catalogs — default: N deps; ng21: N deps; ng19: N deps
```
<test/lint status; note deploy stages correctly skip on feature branches>
```

Notes for the author:
- Keep the diff to onboarding only — reviewers reject unrelated resolution
  churn. Run the drift check before every push.
- If onboarding needed a policy change first (e.g. a new `ngNN` cluster catalog for this repo's
  Angular major — cluster membership is derived from `@angular/core`, there is no registry to edit),
  link the `dependency-version-policy` MR here.
- AI review bots re-post the same integrity/packageManager comments on every
  push; answer once, resolve, and reference the earlier thread for repeats.
