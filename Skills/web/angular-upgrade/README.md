# angular-upgrade

Safely upgrade an Angular app to a newer major version through a guided, phased workflow — SSR- and micro-frontend-aware, grounded in Angular's own official migration data, with a human in the loop at every real decision point.

## What it does

Drives an Angular version bump the way a careful engineer would: one small, verifiable change at a time, validated against a build gate after each step, and never batching fixes. It works autonomously on the mechanical parts and pauses to ask you whenever it hits a genuine decision or an unresolvable blocker.

The upgrade runs as a sequence of phases:

- **Pre-flight & planning** — reads `package.json` to detect the current Angular/TypeScript/RxJS/Zone.js versions, resolves the exact target patch, classifies the project (SSR, monorepo, internal packages, micro-frontend), and prints a full upgrade plan before touching anything. Multi-major jumps are done **one major at a time**; monorepos are done **one project at a time**.
- **Dependency upgrade** — bumps Angular and its ecosystem in a strict, dependency-ordered sequence, preferring `ng update` schematics, with a build gate after every package.
- **Official migration-guide audit (100% coverage)** — fetches Angular's own `recommendations.ts` (the structured data behind `angular.dev/update-guide`) straight from the Angular repo and audits **every** applicable item against your codebase. Each item gets an explicit status (already handled / fixed / not applicable / needs manual action) — nothing is silently skipped — and the result is written to an audit log.
- **SSR migration** — for server-rendered apps, updates the server bootstrap and providers, and verifies the SSR server actually **boots and renders** (not just that the build passes) while leaving your custom server concerns (CSP/nonce, redirects, monitoring) untouched.
- **Micro-frontend / Native Federation awareness** — recognizes federated hosts and remotes, keeps the federation adapter version-locked to the Angular major, reconciles shared singletons across the fleet, and enforces host/remote lockstep. (Webpack Module Federation is out of scope — the skill hard-stops rather than guess.)
- **Build fix, lint fix, deprecation sweep, test fix** — iterative, error-driven loops that fix the first error and re-run, with circuit breakers so it escalates instead of looping forever. It won't disable lint rules, skip tests, or reduce coverage to go green.
- **Third-party review** — after the core upgrade is green, brings compatible ecosystem packages up to date and reports the ones that can't move yet.
- **Report & deployment checklist** — produces an upgrade report (with a pass/fail banner, breaking changes, files touched, and performance metrics) plus a deployment checklist that flags things like a required Node.js bump.

Every phase commits its own progress, so a run can be stopped and resumed, and a tripped circuit breaker always leaves you with a committed state and a written explanation.

## When it triggers

Invoke it explicitly with `/angular-upgrade`, or describe the task in natural language, e.g.:

- "upgrade Angular" / "upgrade to Angular X" / "migrate to Angular X"
- "run ng update" / "update Angular version" / "bump the Angular major"
- "bring this repo up to date" (when `angular.json` or `@angular/core` is present)

## Inputs / arguments

- **Target version** (recommended): pass it in the prompt, e.g. `/angular-upgrade 21` or `upgrade to Angular 21.1.0`. A major-only target (`21`) is resolved to the latest stable patch automatically. If no target is given, the skill asks for the target major before doing anything.
- **Project selector** (monorepos): a `--project=<name>` hint, or the skill will ask which project to target.

The current ("from") version is always read from `@angular/core` — you're never asked for it.

## Requirements

- **Claude Code** with this skill installed.
- **An Angular repository** — a workspace with `angular.json` and `@angular/core` in `package.json`.
- **Node.js and the project's package manager** (npm / pnpm / yarn) available on the machine.
- **Network access** to fetch Angular's official update data (`recommendations.ts`) from GitHub. If unreachable, it falls back to the release notes/blog.
- **A private-registry login** — only if the project depends on privately published packages, so they can be installed and (where needed) upgraded.
- **A GitLab token** — only if you use the optional, read-only federation-discovery script to inventory a multi-repo micro-frontend fleet. It's not needed for a standard single-app upgrade.

Run it locally and supervised. This is a human-in-the-loop workflow — Angular upgrades are too interactive to delegate end-to-end to an unattended CI job.

## Not for

This skill **changes the Angular version**. Adopting new APIs, migrating to signals, or cleaning up patterns **on the version you're already on** is a separate concern — that's same-version modernization, not a version upgrade — and belongs in a dedicated modernization skill rather than here.
