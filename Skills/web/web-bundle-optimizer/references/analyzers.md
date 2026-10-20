# How the analyzer works, and how to read it

## The metafile

`ng build --stats-json` on an esbuild builder writes `stats.json`, which is an
[esbuild metafile](https://esbuild.github.io/api/#metafile):

```jsonc
{
  "inputs":  { "src/main.ts": { "bytes": 812, "imports": [...] }, ... },
  "outputs": {
    "dist/browser/main-ABC123.js": {
      "bytes": 315822,
      "entryPoint": "src/main.ts",
      "imports": [
        { "path": "dist/browser/chunk-XYZ.js", "kind": "import-statement" },
        { "path": "dist/browser/chunk-LAZY.js", "kind": "dynamic-import" }
      ],
      "inputs": { "node_modules/swiper/element/bundle.mjs": { "bytesInOutput": 181624 }, ... }
    }
  }
}
```

Two fields carry the whole analysis:

- `imports[].kind` — `dynamic-import` is the lazy boundary. Every other kind is eager.
- `inputs[].bytesInOutput` — post-tree-shaking, post-minification bytes that this specific input
  contributed to this specific output. This is the number to attribute, **not** the input's
  `bytes`, which is its pre-bundling size.

## The eager set

`analyze-bundle.mjs` seeds a queue with the initial scripts named by the generated
`index.html` / `index.csr.html` — its `<script src>` and `<link rel="modulepreload">` tags, i.e.
the browser's own definition of what loads first — then walks `imports` transitively, skipping
`dynamic-import` edges. The visited set is the eager set.

`entryPoint` cannot seed this walk: Angular's esbuild build emits an `entryPoint` for every
lazily-loaded component, so nearly every chunk carries one and seeding from them marks the whole
application eager. It is kept only as a fallback (`src/main.ts`) for builds with no index HTML on
disk.

This matters because filename heuristics lie. `main-*.js` is usually only 10–15% of what the
browser downloads first; the rest sits in `chunk-*.js` files that `main` statically imports and
that the `<link rel="modulepreload">` tags in `index.html` pull in. Reporting `main-*.js` alone
understates first load by a large factor — which is why the skill always reports both.

## Package attribution

Every input path is mapped to a package by taking the segment after the last `node_modules/`,
keeping scoped names whole (`@angular/core`, not `@angular`). Inputs with no `node_modules/`
segment are bucketed as `src (app code)`.

The "last" occurrence matters: a nested dependency lives at
`node_modules/a/node_modules/b/index.js` and belongs to `b`, not `a`.

## Gzip

The script gzips the emitted file from disk when it can find it next to `stats.json`, which is the
number that matches what a browser downloads. When the file is absent (metafile copied elsewhere)
it falls back to `raw * 0.29` and that estimate is clearly a fallback — prefer running the script
against a real `dist/`.

## Reading the output

`bundle-report.md`:

- **Eager JS** — the honest first-load number. Track its gzip value over time.
- **`main-*.js`** — the OKR-facing number.
- **Top packages in the eager set** — the ranked candidate list. Framework entries
  (`@angular/core`, `rxjs`) are largely irreducible; ignore them and look at the rest.
- **Eager chunks + top contributors** — tells you *which* chunk to attack and what dominates it.
- **Reduction opportunities (ranked)** — the same packages, minus the framework floor, each tagged
  with the playbook pattern that applies and its share of the eager set. Coarse by design: it
  ranks candidates, it never claims a saving. A package with no pattern match means "read the
  importing chunk before acting", not "irreducible".

`bundle-report.json` is the machine-readable form and the input to `compare-bundle.mjs`. It is
`schema: 2` since the `opportunities` array was added; a `schema: 1` baseline still diffs fine,
the delta just has no "what to improve next" table.

## Reading a delta

`compare-bundle.mjs` prints per-metric deltas plus a "packages that moved" table. Interpretation:

| Observation | Meaning |
| --- | --- |
| package gone from the eager set (`after` = 0) | fully deferred — the intended outcome |
| package shrank but stayed | partially deferred; some other eager path still reaches it. Find it before claiming the win |
| eager JS down, total JS up | correct and expected — the bytes moved to a lazy chunk |
| eager JS down, total JS down by the same amount | the code was *deleted*, not deferred. Confirm that was intended |
| `main` down, eager flat | the code moved between eager chunks. **No user-visible win.** Do not report it as one |

That last row is the most common way a bundle "optimization" fools its author. The eager number
is the one that cannot be gamed by moving code between statically-imported chunks.

`compare-bundle.mjs` states this itself in a **Verdict** section rather than leaving it to the
reader — it labels a `main`-only drop as a relocation, flags an eager-set regression as
revert-worthy, and separates packages that left the eager set from those that merely shrank.
`--goal <pct> --metric <m>` adds the remaining KB to the target, and the delta closes with the
ranked **What to improve next** table carried over from the current report's `opportunities`.
Those three sections are what the report's conclusion is written from.

## Limitations

- Assumes the esbuild application builder. See `references/detection.md`.
- Native-federation remotes each have their own eager set; analyze them one at a time.
- Server bundles (`dist/server/`) are excluded by design — they are not downloaded by users.
- CSS is reported but not attributed per package; esbuild metafiles do not carry enough
  information to do that reliably.
