# Angular budgets and the ratchet

## What each budget type counts

| `type` | Counts | Useful for |
| --- | --- | --- |
| `initial` | every file the browser loads before any lazy route — all eager JS **plus** the initial CSS | **the one that matters**; it is the only type that constrains the eager set |
| `bundle` + `name` | one named bundle only | a single entry point, e.g. `main` |
| `allScript` | every emitted `.js`, eager and lazy | grows whenever a lazy route is added — noisy, weak signal |
| `any` / `anyScript` / `anyComponentStyle` | per-file caps | catching one runaway file or stylesheet |

`ng build` warns at `maximumWarning` and **fails** at `maximumError`, so a budget error is already
a CI gate in any pipeline that runs the production build. No new stage is needed.

## The most common misconfiguration

```jsonc
"budgets": [{ "type": "bundle", "name": "main", "maximumWarning": "870kb", "maximumError": "3.1mb" }]
```

This looks like protection and is not. It constrains one entry point, while the eager set — which
can be several megabytes across statically-imported `chunk-*.js` files — is completely
unconstrained. Worse, it is gameable in the wrong direction: code moved out of `main` into an
eagerly-imported chunk makes this budget go down while first load is unchanged.

Whenever a repo has no `initial` budget, report it as a finding on its own, separate from any
size reduction.

## The ratchet

After each accepted candidate:

1. Take the **`initial` budget basis** line from `bundle-report.md` — not the eager-JS number.
   `initial` counts eager JS **plus the initial stylesheets**, in raw uncompressed bytes, so
   ratcheting to the eager-JS figure alone sets the ceiling below what the build already emits and
   the very next build fails. On the reference app (a large Angular SSR site) the gap is ~258 KB of CSS.
2. Use the thresholds the report prints (`suggestedWarningKb` / `suggestedErrorKb` in the JSON):
   - `maximumWarning` = measured + ~3%
   - `maximumError` = measured + ~8%
3. Commit the budget change together with the code change, so the win and its guard land as one.
4. Run the production build once more after editing the budget. A budget that fails on the very
   commit that introduces it is worse than no budget — it trains the team to ignore the warning.

Headroom of 3%/8% absorbs ordinary feature work without letting a large regression through. Do not
leave headroom "for later" — that is how the previous ceiling was lost.

Use `kb` / `mb` units, matching the existing entries in the file.

## Local enforcement in a script

`compare-bundle.mjs --min-reduction <pct> --metric main|eager-gzip|eager-raw` exits 2 when the
reduction target is missed. Useful for a goal-tracking job; the Angular budget remains the gate
that protects `master`.
