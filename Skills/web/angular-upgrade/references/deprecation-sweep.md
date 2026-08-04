# Deprecation Sweep

After all Angular packages are upgraded and the build is green, sweep component code for deprecated patterns.

## Rule

**Deprecated = update it. Supported but old-style = leave it alone.**

The goal is correctness after the upgrade, not a style rewrite.

## What to Update

Scan `src/` for deprecated Angular APIs relevant to the upgraded version:

| Pattern | Replacement | Deprecated Since |
|---------|-------------|------------------|
| `*ngIf` directive | `@if` block | Angular 17+ |
| `*ngFor` directive | `@for` block | Angular 17+ |
| `*ngSwitch` / `*ngSwitchCase` | `@switch` / `@case` | Angular 17+ |
| `HttpClientModule` import | `provideHttpClient()` | Angular 15+ |
| `RouterModule.forRoot()` in standalone | `provideRouter()` | Angular 14+ |
| `BrowserModule` in standalone components | Remove — built-in for standalone | Angular 14+ |
| `ModuleWithProviders` patterns (old) | `EnvironmentProviders` | Angular 14+ |
| `@Inject()` decorator for primitives | `inject()` function | Angular 14+ |
| `TestBed.get()` | `TestBed.inject()` | Angular 9+ |
| `async()` in tests | `waitForAsync()` | Angular 10+ |

Only apply deprecations relevant to **this migration's version range**.

## What NOT to Update

- Code that still works and compiles without warnings
- Any pattern that is "preferred" or "recommended" but not deprecated
- Working test infrastructure that is not causing failures
- Third-party library internals

## Sweep Approach

1. Search `src/` for each known deprecated pattern matching the migration range
2. For each hit: confirm it is genuinely deprecated in the target version
3. Apply the replacement
4. Run the build after the sweep to confirm nothing broke
5. Commit the sweep:
   ```bash
   git add -A
   git commit -m "chore: replace deprecated Angular APIs after v{FROM}→v{TO} upgrade"
   ```
