# Lint Fix Strategy

This document defines the anti-loop strategy for fixing ESLint errors after Angular upgrades.

## The Loop Problem

From previous upgrade experiences, AI agents would:
1. Run lint, see 200+ errors
2. Start fixing errors one by one
3. Some fixes introduce new errors
4. After fixing ~50, the AI gets confused and starts reverting fixes or overriding rules
5. Goes into an infinite loop

## Anti-Loop Strategy

### Rule 1: Auto-fix first

Always start with the auto-fixer:
```bash
pnpm lint:fix
```

This handles the majority of mechanical fixes (import ordering, formatting, simple replacements).

### Rule 2: Group by rule code

After auto-fix, run lint and categorize remaining errors. Use ESLint's machine-readable JSON output — a `grep -oP '@[a-z-]+/[a-z-]+'` over the stylish formatter silently drops every **unscoped** built-in rule (`no-console`, `prefer-const`, `eqeqeq`, …), so the agent prioritises the wrong rules:
```bash
pnpm lint -- --format=json 2>/dev/null > AI/lint.json
jq -r '[.[].messages[].ruleId // "no-rule"] | group_by(.) | map({rule: .[0], count: length}) | sort_by(-.count)[] | "\(.count)\t\(.rule)"' AI/lint.json
```

This gives you a frequency-sorted list of ALL rule violations (scoped and unscoped). Example output:
```
  45 @typescript-eslint/no-unused-vars
  23 @angular-eslint/no-empty-lifecycle-method
  15 no-console
   8 @typescript-eslint/prefer-readonly
```

(If `jq` isn't available, fall back to `pnpm lint -- --format=compact` and group on the `[error/<rule>]` token — but the JSON path is preferred.)

### Rule 3: Fix one rule category at a time

Pick the most frequent rule and fix ALL instances of that rule before moving to the next.

For each rule:
1. Search for all files with that specific error
2. Apply the fix pattern across all files
3. Re-run lint to verify the rule is resolved
4. Move to the next rule

### Rule 4: Maximum 2 iterations per rule

If a rule's error count doesn't decrease after 2 fix attempts, skip it and move on. Report it to the user.

### Rule 5: Track progress

After each round of fixes, count remaining errors from the JSON output. A `grep -c 'error'` over stdout is unreliable — it counts the literal word in `Parsing error:`, in filenames, in ESLint's own "N errors" summary, and in stack traces, so the circuit breaker trips spuriously or never trips:
```bash
pnpm lint -- --format=json 2>/dev/null > AI/lint.json
jq '[.[].errorCount] | add // 0' AI/lint.json
```

If the error count is not decreasing between rounds, stop and escalate.

## Common Post-Upgrade Lint Errors and Fixes

### `@typescript-eslint/no-unused-vars`
**Cause**: Angular upgrade changes APIs, leaving previously-used imports unused.
**Fix**: Remove the unused import. Do not add `_` prefix - just delete it.

### `@angular-eslint/no-empty-lifecycle-method`
**Cause**: Empty `ngOnInit()`, `ngOnDestroy()`, etc.
**Fix**: Remove the empty method entirely if it does nothing. If it was a placeholder, it's safe to remove.

### `@angular-eslint/no-input-rename`
**Cause**: `@Input('alias') prop` pattern.
**Fix**: Remove the alias: `@Input() alias` and update all template references.

### `@typescript-eslint/prefer-readonly`
**Cause**: Class properties that are never reassigned.
**Fix**: Add `readonly` modifier.

### `@angular-eslint/prefer-standalone`
**Cause**: Components not marked as standalone.
**Fix**: DO NOT convert existing components to standalone. This rule may fire but converting module-based components to standalone is a refactoring task, not an upgrade requirement. If the upgrade does not require standalone conversion, leave it.

### `@angular-eslint/no-async-subscribe`
**Cause**: Using `async` in subscribe callbacks.
**Fix**: Move async logic to a separate method or use `firstValueFrom`/`lastValueFrom`.

### `@typescript-eslint/no-explicit-any`
**Cause**: `any` type usage.
**Fix**: Only fix in NEW code added by the upgrade. Do not refactor existing `any` types.

## Hard Prohibitions

- **NEVER add eslint-disable comments** to suppress errors
- **NEVER modify `.eslintrc`, `eslint.config.mjs`, `.prettierrc`, or `@your-org/eslint-config`** rules
- **NEVER change lint rule severity** (error → warning)
- **NEVER add rule overrides** in angular.json or component-level configs

If a lint rule cannot be satisfied without a significant refactor, document it and ask the user.

## Circuit Breaker

After 3 full rounds (lint → fix → lint) with no progress (error count not decreasing):
1. Stop fixing
2. Count and categorize remaining errors
3. Report to the user which rules still have violations and how many
4. Ask for guidance on whether to:
   a. Continue with a specific fix strategy
   b. Skip remaining lint errors
   c. Address specific rules manually
