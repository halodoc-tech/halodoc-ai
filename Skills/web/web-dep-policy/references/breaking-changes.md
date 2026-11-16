# Breaking-change recipes for the governed dependency set

Recipes marked **VERIFIED** were executed on real repos during the pilots; the
rest summarize each package's documented breaking surface for the major line the
policy currently pins. Always follow the general procedure at the bottom for
anything not listed.

## eslint 9.x → 10.x  — VERIFIED (a micro-app onboarding)

Symptom when only eslint is bumped:
```
TypeError: Class extends value undefined is not a constructor or null
    at .../@typescript-eslint+utils@<old>.../FlatESLint.js
```
Immediate cause: that `@typescript-eslint/*` version extends eslint's removed
`FlatESLint` shim and peers only `^8.57 || ^9`. Everything in the family must
resolve to a version peering `^10` (≥ <new>).

**Root cause is STALE LOCKFILE RESIDUE, not a version conflict — and that
determines the fix.** Nothing in the graph actually requires the old version:

```
typescript-eslint@<new>                -> @typescript-eslint/utils: <new>          EXACT
@typescript-eslint/eslint-plugin@<new> -> @typescript-eslint/utils: <new>          EXACT
@angular-eslint/eslint-plugin@<ver>    -> @typescript-eslint/utils: ^7 || ^8   wide
```

The `@typescript-eslint` monorepo pins its own internals EXACTLY, while
`angular-eslint` peers them loosely. An old resolution survives an eslint bump
purely because it still satisfies that wide range, and pnpm does not re-resolve
a satisfied range. Verified: resolving the same package.json from scratch with no
lockfile converges the whole family on ONE version unprompted.

Consequences worth internalising:
- Do NOT reach for a `pnpm.overrides` entry. It appears to work but only masks
  the staleness — it pins one family member off its siblings and leaves the graph
  inconsistent (a stray types-only package at the old version persisted).
- Do NOT add `@typescript-eslint/utils` to the policy. It is nobody's direct
  dependency and `typescript-eslint` determines it exactly, so governing the
  meta-package is necessary and sufficient. A catalog entry for it would be inert
  (catalogs only bind DECLARED deps) and a `singletonOverrides` entry would be
  masking, not fixing.
- The right fix is to flush the stale entries. No version needs to move.

Fix (surgical — do NOT run bare `pnpm dedupe`, it garbage-collects unrelated
duplicate entries fleet-wide and bloats the MR diff from ~1k to ~3k lines):
1. `grep -n '@typescript-eslint/utils@' pnpm-lock.yaml` — find versions < <new>.
2. If a compatible version already exists in the lockfile (usual case): edit the
   lockfile — delete the old-version definition blocks (`packages:` and
   `snapshots:` sections) for the whole old `@typescript-eslint/*` family, then
   rewrite the remaining references (both key-form `...@<old>(...)` and
   value-form `'@typescript-eslint/utils': <old>(...)`) to the new version.
3. Stale references appear in THREE forms and every one must be rewritten or the
   lockfile breaks with `ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY`:
   - the `'<pkg>@<old>':` definition block under `packages:`
   - the `'<pkg>@<old>': {}` line under `snapshots:`
   - key-form peer suffixes — `...(@typescript-eslint/types@<old>)...`
   - value-form entries — `'@typescript-eslint/types': <old>` ← **most easily
     missed**; it is indented under a dependent and looks nothing like the others.
4. Validate: `pnpm install --frozen-lockfile` (proves internal consistency),
   then run the exact CI lint command (usually `pnpm run lint-report`).
5. If no compatible version exists in the lockfile: bump the direct
   `typescript-eslint` devDependency instead and do a normal install.
6. Measured cost of the wrong tool, for reference: `pnpm dedupe` fixed the family
   but also bumped ~30 unrelated packages (lodash, qs, socket.io, ws,
   ua-parser-js, semver, tmp).

Also check: `eslint-plugin-*` peers (e.g. `eslint-plugin-unused-imports` warns
on eslint 10 — warning only, lint still runs; note it, don't chase it).

## husky 8.x → 9.x

- Hook files in `.husky/` must drop the two v8 header lines
  (`#!/usr/bin/env sh` + `. "$(dirname -- "$0")/_/husky.sh"`) — v9 prints a
  deprecation warning and v10 will hard-fail on them.
- package.json script: `"prepare": "husky install"` → `"prepare": "husky"`.
- `husky add` is gone — hooks are plain files now; edit them directly.
- package.json `"husky": { "hooks": ... }` config blocks (v4 leftovers, present
  in some repos) are ignored by v8+ anyway — delete them in passing.

## ua-parser-js 1.x → 2.x  — VERIFIED (a website onboarding)

- 2.x is ESM-first with an exports map: deep imports and
  `require('ua-parser-js/package.json')` fail (`ERR_PACKAGE_PATH_NOT_EXPORTED`).
  Import the root only: `import { UAParser } from 'ua-parser-js'`.
- Constructor/getters survive; `getResult()` shape adds `withClientHints()` —
  check call sites that destructure the result.
- If the repo is on 1.x, also re-check `@types/ua-parser-js` — 2.x ships its
  own types; remove the DT package.

## pdfjs-dist 4.x → 5.x

- Worker entry renamed/moved: set
  `GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()`
  (the `.js` worker paths from 2.x/4.x no longer exist).
- 5.x is ESM-only with top-level await — Angular builds need the esbuild
  builder (`@angular/build`), fine on recent Angular majors; webpack-builder repos will choke.
- `ng2-pdf-viewer` / `ngx-extended-pdf-viewer` each pin their own compatible
  pdfjs-dist — bump the viewer to the policy version FIRST, and only align
  pdfjs-dist to what that viewer's peer range wants.

## @ngx-translate/core 14/15/17 → policy version

- v15+: `TranslateModule.forRoot()` unchanged, but standalone-API repos should
  use `provideTranslateService()`.
- v16+ renamed the loader pairing: keep `@ngx-translate/http-loader` in
  lockstep (its major tracks core's).
- The classic breakage is a **peer conflict**, not an API one — core's peer
  range must include the repo's Angular major. The policy placed the version by
  verified peer ranges; if install peers fail, the repo's Angular version is the
  problem, not the policy.

## ngx-quill / ngx-mask / ngx-device-detector / ngx-infinite-scroll

These track the Angular major (that's why they live in the per-Angular-major cluster
catalogs, not the global one). Rules:
- Only convert them to `catalog:<cluster>` when the repo's `@angular/core` major
  matches the cluster. There is NO repo registry in `policy.json` — the guard
  derives the cluster from `@angular/core` and only fails on a mismatch. (Older
  guidance here claimed registration was required; it never was.) What CAN block
  you is the policy having no entry for that dep in your cluster —
  `ERR_PNPM_CATALOG_ENTRY_NOT_FOUND_FOR_SPEC`, which needs a policy MR.
- Their majors are mostly mechanical renames: check each package's release
  notes for the module-import rename of that major (e.g. `QuillModule.forRoot()`
  config moves, `ngx-mask` v-major provider function `provideNgxMask()`,
  `NgxMaskDirective` standalone imports).
- ngx-device-detector/ngx-infinite-scroll on a NEWER Angular than their peer
  range: apps in the fleet already run with peer warnings — treat warnings as
  acceptable, runtime breakage as not.

## xss 1.0.x

Patch-line only in the policy; no breaking surface. If a future policy moves it
a major: the `whiteList` option was renamed `allowList` (aliased, both work).

## lodash / sass / @fingerprintjs/fingerprintjs

- lodash: policy pins a 4.x patch — no API surface change; the pin usually
  lives in `pnpm.overrides` (transitive protection), keep override + catalog in
  sync.
- sass: minor bumps can add deprecation WARNINGS (legacy JS API, slash-div) —
  builds stay green; fix warnings opportunistically, not in the onboarding MR.
- fingerprintjs 4→5: `FingerprintJS.load()` unchanged for the OSS package;
  v5 removed the `monitoring` option — delete it if passed.

## General procedure for an unlisted major

1. `npm view <dep>@<policy-version> peerDependencies` — peer conflicts first; if
   peers exclude the repo's Angular/toolchain the policy version is wrong for this
   cluster: raise it with the policy owners. Note you cannot simply leave the dep
   on a literal version while you wait — the local-pin guard fails the install
   (see SKILL.md Phase 1); it needs an `exceptionCatalogs` entry or the repo stays
   unpinned.
2. `npm view <dep> repository.url` → fetch CHANGELOG/releases for every major
   between current and target; list the breaking items.
3. `grep -rn "from '<dep>" src/` (+ `require(`) — map each breaking item to
   actual call sites; many majors turn out to be irrelevant to how the repo
   uses the package.
4. Apply fixes, then run: typecheck/build, unit tests, lint. Iterate on errors.
5. Can't get green? Reverting that pointer to a literal version does NOT work —
   the local-pin guard fails the install. Either land an `exceptionCatalogs` entry
   for the dep (policy MR to `stage-release`) or park the whole onboarding by
   dropping the config dependency. Record which, and why, in the MR.
