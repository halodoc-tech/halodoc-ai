# Internal shared libraries — attributing the eager set to a repo

A per-package size table tells you *what* is big. It does not tell you *whose problem it is*, and
in a typical org that is usually the deciding question: most of a web app's eager set belongs to
internal libraries published from a handful of shared repos, and half the plausible fixes are not
in the app at all.

`analyze-deps.mjs` answers three questions the bundle report cannot:

1. **which repo owns each eager byte** — `@design-system/*` → `libs/design-system`,
   `@web-shared/*` → `libs/web-shared`, `@your-org/*` → `libs/commons`;
2. **whether the cost is packaging or usage** — an upstream defect versus the app's own choices;
3. **which internal library requires each eager third-party package** — the reason a dependency
   the app "owns" often cannot be removed by the app.

```bash
node <SKILL_DIR>/scripts/analyze-deps.mjs \
  --report bundle-report.json \
  --repos-root .. \
  --scopes @design-system,@web-shared,@your-org --owner-hosts git.example.com \
  --md bundle-deps.md
```

`--repos-root` is scanned for local clones so a finding can name the repo and path an upstream MR
would touch; libraries whose repo is not cloned are still reported, marked unresolved. The scan
looks for `projects/*/package.json`, `libs/*`, `packages/*` — the Angular workspace layouts.

## What counts as ours

`--scopes` seeds the list; a manifest whose `repository`/`homepage` points at one of `--owner-hosts` counts
too, so unscoped internal names (`design-system`, `web-shared`) are picked up without listing them in `--scopes`.

Everything below — the packaging signals, the verdict, the fix list — applies to owned packages
only. For a package we do not publish, "missing `sideEffects: false`" is not a finding: there is no
MR to raise, and pinning a fork to make a number move is not a fix. Third-party packages appear in
the report solely under *who requires them*, because the only lever we have over them is when our
own code pulls them in.

## Packaging or usage

The verdict per library comes from facts read off the installed package, not from guesswork:

| Signal | Where | What it means |
| --- | --- | --- |
| `sideEffects` | published `package.json` | anything other than `false` forces the bundler to keep every imported module. **Blocker.** |
| NgModules in output | `ɵɵdefineNgModule` in the FESM | importing one component pulls in every declaration its module lists. **Blocker.** |
| heavy hard dependency | published `dependencies` | `crypto-js`, `moment`, `@angular/material`… every consumer inherits it. **Blocker.** |
| subpath `exports` | published `package.json` | informational only — see below |
| retained % | eager bytes ÷ published bytes | direction only — the numerator is minified and the denominator is not |

| shake probe | measured with the repo's esbuild | one symbol costs ~the whole barrel ⇒ the entry point is indivisible. **Blocker, and it outranks every inferred signal above.** |

Any blocker ⇒ the fix is **upstream**, in the owning repo. No blocker ⇒ **consumer**: what ships is
what the app references, so the lever is deferring the usage.

### The shake probe — measure, do not infer

`sideEffects: false` and "no NgModules" are necessary, not sufficient, and trusting them produced a
wrong verdict on a real repo. The probe bundles two entries with the repo's own esbuild — one
importing a single non-component export, one importing the whole barrel — and compares. A ratio
near 1 means nothing can be imported in isolation.

On the reference app (a large Angular SSR site), every eager internal library failed it:

| Package | Probe symbol | One symbol | Whole barrel | Retained |
| --- | --- | ---: | ---: | ---: |
| `@design-system/molecules` | `SOME_CONSTANT` | 566.3 KB | 570.1 KB | 99% |
| `@design-system/organisms` | `SomeEnum` | 528.7 KB | 529.9 KB | 100% |
| `@design-system/templates` | `SomeModel` | 325.4 KB | 326.0 KB | 100% |
| `@design-system/atoms` | `SOME_URL` | 260.6 KB | 262.0 KB | 99% |
| `@web-shared/feature-a` | `FeatureAType` | 122.8 KB | 123.3 KB | 100% |
| `@web-shared/shared` | `SomeService` | 126.9 KB | 131.1 KB | 97% |
| `@web-shared/core` | `SOME_CONSTANT` | 87.5 KB | 97.5 KB | 90% |
| `@web-shared/auth` | `SOME_CONFIG` | 54.6 KB | 55.1 KB | 99% |

Importing one string constant from `@design-system/atoms` costs 260 KB. The real CLI build agrees: an
`app.component.ts` import of the two-member enum is the *only* eager reference to
`@design-system/templates`, and 157.3 KB of it lands in the eager set.

Cause: ng-packagr emits the library as one internal chunk module which the barrel re-exports.
`sideEffects: false` licenses dropping unused *modules*, and there is only one module, so there is
nothing to drop. This is the case — and the only case — where adding secondary entry points is the
fix rather than a pointless refactor across every consumer.

Rules for the probe:

- **a non-component symbol** is chosen deliberately (service, model, enum, token). A component
  legitimately drags its template's dependencies along and would make a healthy library look broken.
- **a skipped probe is unknown, never a pass.** No esbuild resolvable, no named exports, a failed
  build — all report `not measured`, and the reasons say packaging is *unverified*.
- probes run only for packages above the 20 KB floor: two esbuild builds each, ~1s for a whole app.

### The trap: "no subpath exports" is not a defect

The tempting finding is that a library exposes one entry point, so consumers "must import the
whole barrel" — followed by a recommendation to add secondary entry points and rewrite every
import to a deep path. That recommendation is wrong for a library that already sets
`sideEffects: false` and ships ESM. esbuild drops unused top-level symbols from a single flat FESM
exactly as well as from ten entry points. The refactor touches every consumer and saves nothing.

This is why the script reports subpaths but only escalates them when something *else* already
blocks shaking — and the shake probe above is how it finds out. Single entry point,
`sideEffects: false` and zero NgModules look correctly packaged on paper; `@design-system/*` has all
three and still retains 90–100% of the barrel, because ng-packagr emitted it as one chunk module.
So: probe passes → a missing subpath is not a finding, fix usage in the app. Probe fails → the
library needs a secondary entry point upstream (on the reference app, a new
`@design-system/templates/scrolling` entry point is what took 157.3 KB out of the eager set).

### Reading the retained %

Eager bytes are minified; published bytes are not. Minification alone typically removes half. So
~40% retained does **not** mean "60% was tree-shaken" — it means little beyond minification came
off, i.e. the app really does reference most of the library. Use it to compare libraries against
each other, never as an absolute shaking score, and never quote it as a saving.

## The last-eager-importer rule

```bash
node <SKILL_DIR>/scripts/analyze-deps.mjs --trace @design-system/atoms --dist dist
```

A chunk leaves the eager set only when its **last** eager importer leaves. Nothing partial counts,
and the importers are rarely all in app code.

The case that produced this rule, on the reference app (a large Angular SSR site): `@design-system/atoms` was 138.2 KB of
the eager set, and a `src/`-only scan showed exactly two importers — `alerts-box` and
`upgrade-notification`, both conditional, browser-only shell UI. Deferring both looked like a
certain 138 KB. Measured result: **6 KB**, from the app components themselves moving to a lazy
chunk. `@design-system/molecules`, `@design-system/organisms`, `@design-system/templates` and four `@web-shared`
packages all import atoms as well, and every one of them was still eager, so the chunk never
moved. The candidate was reverted and demoted to REPORT.

Two lessons, both encoded in `--trace`:

- **library-to-library edges are first-class.** A `grep` over `src/` systematically overstates what
  deferring will achieve, because it cannot see `@web-shared/shared → @design-system/atoms`.
- **shared foundational packages are the wrong first target.** The lower a package sits in the
  dependency graph, the more eager importers it has, and the less any single defer accomplishes.
  Attack a package with few importers, or a whole cluster at once.

## Shared dependencies are cross-repo work

The table of who requires each eager third-party package is the one that changes plans.
`@angular/material` may be the largest single eager package and be declared by the app — but when
five internal libraries also require it, no amount of local import hygiene removes it. While those
libraries are in the eager graph, Material comes with them.

Both `dependencies` and `peerDependencies` count here. A peer the app happens to satisfy is still
a dependency the app cannot unilaterally drop.

Consequence for sequencing: attack the **library's eagerness** (defer the shell components that
pull it in) before attacking the third-party package it drags along. Removing Material from the
app's imports while `@web-shared/shared` still renders eagerly moves nothing.

## The fix list

The verdict says who owns the fix; `bundle-deps.md`'s **How to fix each owned dependency** section
says what the fix is. Each item carries four fields, and all four exist because a finding without
them gets read, agreed with, and not done:

- **Where** — the file, resolved to the local clone's path when `--repos-root` finds it.
- **Why it costs** — the mechanism, with the current bytes. Not a predicted saving.
- **How** — the concrete edit, including the migration that keeps it non-breaking.
- **Proof** — the command whose output changes if the fix landed.

The fix list reads the metafile too, so the `consumer` item names the **actual** importers instead
of a pattern: the `src/` files to change, and the library modules that also hold the package eager.
When any library importer exists the item is marked *blocked* — deferring the app files alone frees
nothing, so the candidate is either widened to the whole cluster or dropped. Packages under 20 KB
get no block; they stay in the tables, because a fix worth 3 KB of a 2.5 MB eager set costs more
attention than it returns.

Worked example, the reference app (a large Angular SSR site) at the Swiper commit: `@design-system/templates` (157.3 KB) has
exactly one importer, `src/app/app.component.ts`, and no library importer — the cheapest real
candidate on the list. `@design-system/molecules` (239.8 KB) is bigger and has *no* app importer at all:
six libraries reach it, so nothing in the app can move it directly. The size ranking and the work
ranking are not the same list, which is the whole reason this section exists.

Every owned package in the eager set ends with a `consumer` item even when the packaging is clean,
because packaging decides *how much* ships and eagerness decides *when*. A library with a perfect
manifest still costs the full first-load wait while the shell renders it.

## The ranked plan is the deliverable

Everything above explains *why* bytes are eager. Only the ranked plan says *where the KB are and
how many*, and it is the section to lead with — a reader who gets mechanism instead of a number
cannot act, and will ask for the number.

It is a simulation, not an estimate: cut the import edges the edit would cut, recompute what is
still reachable from the eager entry points, sum the eager bytes that fell out. Consequences worth
knowing:

- **a blocked candidate scores ~0 KB by arithmetic**, so the last-eager-importer rule enforces
  itself instead of relying on a warning.
- **candidates must be edits that exist.** Ranking "load `app.component.ts` lazily" once produced a
  plan claiming 85% of the eager set — true on the graph, impossible to execute, because the root
  component is what bootstraps. The unit is therefore an import *edge*, plus lazy-loading for
  non-shell files.
- **the greedy pass re-simulates** with earlier cuts applied, because two edits that free the same
  shared chunk are worth one saving. Summing per-candidate savings overstates every plan.

- **the plan spans repos, and says which one.** Restricting it to app code stops at 12.9% here and
  reads as a ceiling. Library-to-library edges are candidates too — they are simply another repo's
  MR, and the two `@design-system/*` -> `@angular/material` rows are worth more than everything the app
  can do. Candidates are generated only for source packages your org owns.
- **greedy means re-scoring, not sorting once.** Marginal savings move as cuts land: on this repo
  `@design-system/atoms` -> `@angular/material` is 87 KB standalone and 174.9 KB once molecules has been
  cut, so a sort-once plan buries the largest row. Pick the best marginal each iteration.
- **barrel splits cannot be simulated**, because splitting changes how many bytes ride an edge, not
  whether the edge is reachable. They are estimated from symbols-named ÷ symbols-exported, labelled
  as estimates, and kept out of the simulated total.

the reference app (a large Angular SSR site), at the Swiper commit: seven simulated edits, 707.8 KB raw / ~181 KB
gzip, 28.6% of the eager set — 342.2 KB in the app, 261.9 KB in `design-system`, 103.7 KB in
`web-shared` — plus ~640 KB of barrel-split estimates on top. Report the split by repo: a
number that needs another team's merge is not a number this MR delivers.

## Turning a finding into work

- **consumer** → a candidate in this repo, following the playbook, measured the usual way.
- **upstream** → an issue or MR on the owning repo, quoting the eager bytes and the specific
  packaging fact. Do not fix it by patching `node_modules` or by pinning a fork.
- **shared third-party** → coordinate: the app change and the library change land in an order that
  actually moves the metafile, and the OKR owner needs to know it spans repos.

State plainly, in the report, which findings are outside the repo being optimized. A number that
requires another team's merge is not a number this MR delivers.
