# web-dep-policy

A Claude Code skill that onboards a web app to a **central dependency version
policy** — a single package, shipped as a pnpm 10 **config dependency**, that
governs shared dependency versions across many independently deployed
frontends — and keeps an already-onboarded app current.

## What it does

- **Audits** the repo against the newest published policy and classifies every
  governed dependency as same / patch / minor / **major**.
- **Flags major bumps** before touching anything (they need an explicit
  remediate-or-exception decision).
- **Migrates pnpm 8 → 10** with a zero-drift lockfile conversion when needed.
- **Converts** hardcoded versions to `catalog:` pointers and **repins** the
  config dependency (exact version + integrity hash).
- **Applies known breaking-change fixes** (eslint 10, husky 9, pdfjs-dist 5,
  ngx-* majors) — see `references/breaking-changes.md`.
- **Validates** against the CI Dependency Policy Gate.

## Usage

Invoke the skill and point it at a repo you want to onboard or update. It runs
`scripts/version-audit.mjs` first to decide onboard vs. update, then follows the
phased workflow in `SKILL.md`.

## Layout

- `SKILL.md` — the full workflow (mode selection, onboarding phases, update
  flow, breaking-change remediation).
- `references/breaking-changes.md` — verified recipes for the governed
  dependency set.
- `references/mr-template.md` — the onboarding merge-request template.
- `scripts/version-audit.mjs` — repo-vs-policy audit (set your registry with
  `--registry`).
- `scripts/lockfile-drift-check.py` — proves a lockfile change introduced only
  the approved version bumps.

> Identifiers in this skill (package scope `@your-org/…`, the registry host,
> repo paths, CI helper names) are placeholders — swap them for your
> organization's.
