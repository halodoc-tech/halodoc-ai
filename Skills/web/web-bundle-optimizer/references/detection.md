# Toolchain detection

Everything here is a lookup. Never assume a value that can be read.

## Builder — decides whether this skill can run at all

`angular.json` → `projects.<name>.architect.build.builder` (Angular 17+ may spell it
`projects.<name>.targets.build.builder`).

| Builder string | Meaning | Action |
| --- | --- | --- |
| `@angular/build:application` | esbuild, Angular 18+ | supported |
| `@angular-devkit/build-angular:application` | esbuild | supported |
| `@angular-devkit/build-angular:browser-esbuild` | esbuild | supported |
| `@angular-devkit/build-angular:browser` | webpack | **stop** — `--stats-json` emits a webpack stats file, not an esbuild metafile |
| `@angular-architects/native-federation:build` | wraps esbuild | supported, but the eager set is per-remote — analyze each remote separately |

On webpack, say so and stop:

> This repo builds with the webpack browser builder. `analyze-bundle.mjs` reads esbuild
> metafiles only. Either migrate to `@angular/build:application` first, or use
> `webpack-bundle-analyzer` for a one-off look.

A repo can also have `webpack-bundle-analyzer` in `devDependencies` and an `analyze` script
pointed at an esbuild `stats.json` — that combination produces nonsense output. Flag it.

## Package manager

Lockfile decides, in this priority order:

| File | Commands |
| --- | --- |
| `pnpm-lock.yaml` | `pnpm run <script>`, `pnpm dlx` |
| `yarn.lock` | `yarn <script>` |
| `package-lock.json` | `npm run <script>` |

## Build / test / lint commands

From `package.json` → `scripts`. Prefer an existing script over a hand-rolled `ng` invocation, so
the repo's own memory flags and CI parity are preserved.

Common shapes:

- `"build": "node --max-old-space-size=12000 ./node_modules/@angular/cli/bin/ng build --configuration=production"`
  — the large-heap flag is required on big repos; dropping it produces an OOM, not a smaller bundle.
- `"test:ci": "... ng test --no-watch --coverage"` — Vitest or Karma; `karma.conf.js` present means Karma.
- `"lint": "eslint src"`.

Append `--stats-json` to whichever build command you use. If the script already ends in a pipe or
`&&`, invoke `ng build` directly with the same flags rather than appending to the chain.

## Prod configuration name

`angular.json` → `projects.<name>.architect.build.configurations`. Use the one CI deploys from.
When several exist (`production`, `preprod`, `staging`), baseline against `production` and spot
check the others only if their `optimization` blocks differ.

## SSR

Any of `ssr`, `outputMode: "server"`, `server`, or a `prerender` key means SSR is on. Consequences:

- `stats.json` lands under `dist/browser/`, and there is a second `dist/server/` graph that is
  **not** part of the user-facing eager set — the analyzer only reads the path it is given, so
  point it at the browser one.
- Any change that alters rendered markup risks a hydration mismatch. Diff the SSR HTML of an
  affected route before and after.
- `provideClientHydration` with `withIncrementalHydration()` interacts with `@defer`: a deferred
  block that was server-rendered hydrates on its trigger. Read the existing config before adding
  `@defer` blocks.

## Existing budgets

`angular.json` → `configurations.<prod>.budgets`. Record them verbatim in the report. A repo with
only a `bundle`/`main` budget has **no** constraint on the eager set — call that out as a finding
in its own right, independent of any size reduction.
