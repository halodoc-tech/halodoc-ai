# Test Fix Strategy

Strategies for fixing test failures after Angular upgrades.

## Contents
- [Runner scope: Karma vs Vitest](#runner-scope-karma-vs-vitest)
- [Test Infrastructure](#test-infrastructure)
- [Pre-Upgrade Baseline](#pre-upgrade-baseline)
- [Asserting a green suite](#asserting-a-green-suite)
- [Handling Mid-Run Chrome `ERROR`](#handling-mid-run-chrome-error)
- [Extracting Failing Spec Files](#extracting-failing-spec-files)
- [Iterative Fix Process](#iterative-fix-process)
- [Common Test Migration Patterns](#common-test-migration-patterns)
- [Angular 21 Specific: Test Patterns](#angular-21-specific-test-patterns)
- [Test Failure File Format](#test-failure-file-format)
- [Hard Rules](#hard-rules)
- [Coverage Preservation](#coverage-preservation)
- [Schema suppression hides library-contract breakage](#schema-suppression-hides-library-contract-breakage-a-green-suite-is-not-coverage)

> The `## Migration:` / `## Date:` / `## Test command:` lines further down are **inside** the fenced
> failure-file template, not sections of this document — excluded from the contents above deliberately.

## Runner scope: Karma vs Vitest

**This document describes the Karma + Jasmine toolchain.** Repos already migrated to Vitest run the
official `@angular/build:unit-test` builder instead — detected as `{RUNNER}` = `vitest` in Phase 0B
step 5. On those repos:

| Applies to Vitest? | Section |
|---|---|
| ✅ Yes | Failure classification (Infrastructure / regression / flaky), bundling shared-root-cause failures, the failure-file format, hard rules, coverage preservation, schema-suppression guidance |
| ⚠️ Adapted | "Asserting a green suite" (both runners below), extracting failing specs (Vitest prints `FAIL <path>` lines directly — no suite-name→path mapping needed) |
| ❌ No | "Handling Mid-Run Chrome `ERROR`" and every `--browsers` / `--no-code-coverage` / `--include` flag — those are Karma-builder options. The Vitest equivalent of a truncated run is a non-zero `Unhandled Errors` count |

For Vitest-specific failure signatures (browserslist, zone/ProxyZone, TDZ in partial-compiled libs,
`restoreMocks`, `errorOnUnknownElements`, jsdom shims), consult your Vitest toolchain's own migration
notes — each maps to a verified fix.

## Test Infrastructure

Karma path (`{RUNNER}` = `karma`):

- **Framework**: Karma + Jasmine
- **Browser**: ChromeHeadless (for CI)
- **Coverage tool**: karma-coverage
- **Test command**: `pnpm test:headless` or `ng test --watch=false --browsers=ChromeHeadless --code-coverage`
- **CI command**: `pnpm test:ci` (with increased memory: `--max-old-space-size=12000`)

## Pre-Upgrade Baseline

Run the FULL test suite ONCE, capturing streamed output to a log:
```bash
ng test --watch=false --browsers=ChromeHeadless --no-code-coverage 2>&1 | tee AI/test-baseline.log
```

If the run ends with `ERROR`, apply the "Handling mid-run Chrome ERROR" decision tree before moving on.

## Handling Mid-Run Chrome `ERROR`

A mid-run `ERROR` line from Karma is **NOT automatically environmental**. Do not attribute it to "CPU throttling" or "Chrome crash" without evidence. Default assumption: **this is a real failure in app or test code**.

When you see `ERROR` mid-run:

1. **Scan the ENTIRE log, not just the tail.** The real JS stack trace often appears hundreds of lines above the final `DISCONNECTED` / `ERROR` summary — separated by noise. Use grep:
   ```bash
   grep -nE "at [A-Za-z_$][A-Za-z0-9_$]*.*\(src/app/" AI/test-baseline.log
   grep -nE "FAILED$|✗" AI/test-baseline.log
   grep -n "full page reload" AI/test-baseline.log
   ```

2. **A JS stack trace into `src/app/**` is a real bug, full stop.** Fix it. The Karma disconnect is a downstream symptom.

3. **`Some of your tests did a full page reload` is a real bug.** A spec navigated (unmocked `window.location`, form submit, or `ngOnInit` error), killing the Karma runner. Find and fix it.

4. **`Disconnected, because no message in 300000 ms` is a downstream symptom.** Ignore when looking for root cause.

5. Only classify as environmental if ALL hold:
   - No JS stack trace into app code ANYWHERE in the log
   - No `full page reload` marker
   - The message is OOM / disconnect with no preceding app-code trace
   - Same suites pass individually with `--include`

6. **Do not commit and declare completion while a stack trace into `src/app/**` appears anywhere in the log.**

**Mitigations for slow runs** (do not use as excuse to skip investigation):
- Drop `--code-coverage` during iteration to reduce build time and memory
- Tee runs to log files so output is preserved if run ends early

## Extracting Failing Spec Files

From the log, extract unique top-level `describe()` names that failed. Karma prefixes each line with the browser UA — e.g. `Chrome 140.x.x (Mac OS 10.15.7)` on macOS, `(Linux ...)` on CI. Strip everything up to and including the first `)` rather than matching a hardcoded OS version (the old `10.15.7\)` literal silently failed on Linux runners and other macOS patches, shifting `awk`'s columns and mapping the wrong specs):
```bash
grep "FAILED$" AI/test-baseline.log | sed -E 's/^[^)]*\) //' | awk '{print $1}' | sort | uniq -c
```

Map each suite name to its spec file using grep:
```
describe\(\s*['"](SuiteName1|SuiteName2|...)['"]
```
filtered to `**/*.spec.ts`. If a name matches multiple files, run each with `--include` to find the real one.

## Iterative Fix Process

1. Run full suite ONCE (baseline above), tee to log
2. Extract unique failing suite names and map to spec file paths
3. For each failing spec, fix and verify:
   ```bash
   ng test --watch=false --browsers=ChromeHeadless --no-code-coverage --include='**/path/to/failing.component.spec.ts'
   ```
4. After ALL individual fixes pass, run full suite ONE final time in Phase 9
5. **Do NOT re-run the full suite after each fix** — wastes time rebuilding thousands of tests
6. **Do not assume "same spec count → same crash → environmental"** — consistent crash point usually means deterministic bug

## Common Test Migration Patterns

### TestBed API Changes

```typescript
// TestBed.get() → TestBed.inject()
const service = TestBed.inject(MyService);

// TestBed.flushEffects() → TestBed.tick()
TestBed.tick();
```

### Dependency Injection Changes

```typescript
// InjectFlags enum → options object
inject(Service, { optional: true })

// String tokens → InjectionToken
injector.get(MY_TOKEN)
```

### Signal-Based Input Testing

```typescript
// Decorator-based → signal-based
fixture.componentRef.setInput('myInput', 'value');
fixture.detectChanges();
```

### `ng-reflect-*` Attributes

```typescript
TestBed.configureTestingModule({
  providers: [provideNgReflectAttributes()],
});
```

### Uncaught Error Re-throwing

```typescript
// LAST RESORT only
TestBed.configureTestingModule({
  providers: [{ rethrowApplicationErrors: false }],
});
```

### AsyncPipe Error Handling

```typescript
const errorHandler = TestBed.inject(ErrorHandler);
spyOn(errorHandler, 'handleError');
// trigger async pipe error
expect(errorHandler.handleError).toHaveBeenCalled();
```

### DatePipe 'Y' Formatter

```typescript
// Week-numbering year → calendar year
{{ date | date:'yyyy-MM-dd' }}  // lowercase y
```

### Router Testing

```typescript
provideRouter([{ path: '', component: MockComponent }]);
```

## Angular 21 Specific: Test Patterns

### Pattern 1 — `@Input()` inferred as `null` type

Component has `@Input() member = null` (no explicit type). Angular 21 infers as literal `null`. Template `member.property` access (no `?.`) is rejected, causing cascading spec errors.

**Fix in component:**
```typescript
@Input() member: any = null;
// Or for typed inputs:
@Input() details: DetailModel | null = null;
```

### Pattern 2 — Missing `inject()` providers in TestBed

Component uses `inject(SomeService)` but service isn't in TestBed providers.

**Fix in spec:**
```typescript
{
  provide: SomeService,
  useValue: {
    methodUsedInNgOnInit: jasmine.createSpy('methodUsedInNgOnInit'),
    observableUsedInNgOnInit$: EMPTY
  }
}
```

Only mock methods/properties the component actually calls.

### Pattern 3 — Implicit `any` on method parameters (TS7006)

```typescript
// Add explicit : any
handleSelection(selectedInfo: any) { ... }
```

### Pattern 4 — `HttpClientTestingModule` → `provideHttpClientTesting()`

```typescript
// Before
imports: [HttpClientTestingModule]

// After
providers: [
  provideHttpClient(withInterceptorsFromDi()),
  provideHttpClientTesting()
]
```

### Sweep approach for Angular 21 spec fixes

1. Search for `@Input() \w+ = null` (no explicit type) in `*.component.ts`
2. Check template for `inputName.property` access without `?.`
3. If found: change to `@Input() x: any = null`
4. Search for `inject(SomeService)` in components with specs — cross-reference TestBed providers
5. Search for `HttpClientTestingModule` in specs and replace per Pattern 4
6. Run build to confirm, then run targeted spec files

## Test Failure File Format

Record all failures in `AI/angular-upgrade-test-failures.md` (under `AI/` so it stays gitignored and out of the upgrade commits):

```markdown
# Angular Upgrade — Test Failures

## Migration: v{FROM} → v{TO}
## Date: {date}
## Test command: {exact command used}

---

### 1. {Test Suite Name}

**File:** `{path/to/file.spec.ts}`
**Test:** `{describe block} > {it block}`
**Error:**
\```
{exact error message and stack trace}
\```
**Status:** Unresolved / Fixed / Flaky

---
```

### Failure Classification

| Type | Definition | Action |
|------|-----------|--------|
| **Infrastructure failure** | TestBed API change, import path moved, test helper deprecated, provider now required | Auto-fix, re-run only that spec file |
| **Actual regression** | Application logic behaves differently from baseline | Record in failure file, generate report, stop upgrade |
| **Flaky / intermittent** | Fails once but passes on retry | Mark as flaky; do not block on it |

## Hard Rules

- **NEVER use `xit()` or `xdescribe()`** to skip tests
- **NEVER delete test cases** to make the suite pass
- **NEVER remove `expect()` calls** to avoid assertion failures
- **NEVER lower coverage thresholds** in karma config
- If new code was added during the upgrade, add tests to cover it

## Coverage Preservation

This is a **separate, dedicated run with coverage ON** — distinct from the Phase 9 pass/fail run (which uses `--no-code-coverage` for speed). The `Coverage summary` line only appears when coverage is enabled, so the `--no-code-coverage` run can never produce it:

```bash
ng test --watch=false --browsers=ChromeHeadless --code-coverage 2>&1 | grep -A 5 'Coverage summary'
```

Compare with baseline. If coverage dropped, add tests for new/modified code.

## Asserting a green suite

Phase 9 step 4 calls this. Assert the result concretely instead of eyeballing the log — and use the check
that matches `{RUNNER}`, because the two runners print incompatible summaries. Run under `bash`.

**Karma** — injects ANSI colour codes (e.g. `Executed 128 of 128\e[32m SUCCESS`) and prints `SUCCESS`,
not `(0 FAILED)`, so strip ANSI and match loosely or a fully green run reads as a false negative.
`printf '\033'` (not `\x1b`) keeps the strip portable across BSD/macOS and GNU sed:

```bash
esc=$(printf '\033'); clean=$(sed -E "s/${esc}\[[0-9;]*m//g" AI/test-final-v{TO}.log)
if grep -Eq "Executed [0-9]+ of [0-9]+.*SUCCESS|Executed [0-9]+ of [0-9]+ \(0 FAILED\)" <<<"$clean" \
   && ! grep -E "\bERROR\b" <<<"$clean" | grep -vq "console.error"; then
  echo "✅ Suite passing"
else
  echo "❌ Suite NOT passing — failures or a mid-run ERROR present"
fi
```

**Vitest** (`@angular/build:unit-test`) — prints `Tests N passed (N)` and never prints `Executed`, so the
Karma pattern above can never match. A truncated run shows a non-zero `Unhandled Errors` count rather
than a mid-run `ERROR` line — and note the count sits on its own `Errors  1 error` summary line while the
section header `Unhandled Errors` carries no number, so **both** must be checked (matching only
`Unhandled Errors <n>` silently never fires — verified against real output):

```bash
esc=$(printf '\033'); clean=$(sed -E "s/${esc}\[[0-9;]*m//g" AI/test-final-v{TO}.log)
if grep -Eq "Tests +[0-9]+ passed" <<<"$clean" \
   && ! grep -Eq "Tests +.*[0-9]+ failed" <<<"$clean" \
   && ! grep -q "Unhandled Error" <<<"$clean" \
   && ! grep -Eq "^ *Errors +[1-9]" <<<"$clean"; then
  echo "✅ Suite passing"
else
  echo "❌ Suite NOT passing — failures or unhandled errors present"
fi
```

Both checks are **negative-biased on purpose**: an unrecognised summary format falls through to
"NOT passing" rather than reporting a green suite that was never proven.

## Schema suppression hides library-contract breakage (a green suite is not coverage)

`NO_ERRORS_SCHEMA` and `CUSTOM_ELEMENTS_SCHEMA` in a spec's `TestBed` stub out unknown elements and
unknown property bindings. Where the component under test consumes a **library component's outputs**, that
stub makes a binding-name mismatch *undetectable by construction* — the library component is never
instantiated, so nothing can fire its outputs and nothing can notice they aren't wired.

This matters during an upgrade because Angular **does not error on an event binding that matches no
output**: `(onSomethingChanged)="handler($event)"` on a component that no longer declares
`onSomethingChanged` is compiled as a DOM event listener for an event nobody dispatches. It passes the
build, AOT, `strictTemplates`, and lint. Observed in a real upgrade: an internal library dropped the `on`
prefix from its outputs, and the stale bindings shipped to production having survived a fully green
6,298-test suite, because the specs stubbed that component out.

So, when an upgrade bumps a library whose components the app binds outputs to:

- **Render the real component** in at least one spec per binding site instead of stubbing it — import the
  library's module rather than relying on a schema. Library components often need only a small provider
  to construct (e.g. a config token via `SomeModule.forRoot({ apiKey: 'test-key' })`).
- **Prove the guard fails against the old contract.** Temporarily restore the previous binding name and
  confirm the new test goes red, then restore the fix. A test that passes both before and after the fix
  is not a regression guard for this class.
- Do **not** add `NO_ERRORS_SCHEMA` to silence a new unknown-element/unknown-property error introduced by
  the upgrade — that converts a loud, correct failure into a silent one. Fix the binding or the import.

Detecting these mechanically across a repo (rather than per spec) is the subject of an internal-library
API-drift audit — the contract to check is the library's compiled component metadata (`outputs` /
`inputs` public names) versus every template binding.
