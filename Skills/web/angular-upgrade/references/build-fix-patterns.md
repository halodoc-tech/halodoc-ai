# Build Fix Patterns

Error patterns and auto-fix strategies for build failures during Angular upgrades.

## TypeScript Errors

| Error Pattern | Auto-Fix Strategy |
|---------------|-------------------|
| `TS2307: Cannot find module 'X'` | Update import path — check Angular changelog for moved modules |
| `TS2307: Cannot find module '@angular/common/http'` (or any `@angular/*` sub-path) | Fix `moduleResolution` → see `references/tsconfig-migration.md` |
| `TS2339: Property 'X' does not exist` | API removed/renamed — find replacement in Angular migration guide, update all usages |
| `TS2341: Property 'X' is private` | Angular 21 rejects `@HostBinding` on `private` properties — remove the `private` modifier |
| `TS2345 / TS2322: Type errors` | Update type annotation to match new signature |
| `TS2554: Expected 0 arguments, got 1` on `@HostListener` | Decorator passes `['$event']` but handler takes 0 params — remove `['$event']` from decorator |
| `TS7006: Parameter 'x' implicitly has an 'any' type` | Angular 21 enforces `noImplicitAny` — add explicit `: any` annotation |

## Template Errors

| Error Pattern | Auto-Fix Strategy |
|---------------|-------------------|
| Template compilation errors | Update template syntax only if old syntax is no longer accepted |
| Unknown `ngModule` / missing provider | Convert to standalone or update module declaration |
| `Cannot find name 'X'` (removed global) | Add explicit import |

## Style Errors

| Error Pattern | Auto-Fix Strategy |
|---------------|-------------------|
| SCSS/style errors | Check if Angular changed the style preprocessor API; update accordingly |

## SSR Build Errors

| Error Pattern | Auto-Fix Strategy |
|---------------|-------------------|
| `@angular/ssr/node` import errors | Check if APIs were renamed/restructured — see `references/ssr-migration-patterns.md` |
| Vite failing to bundle SSR | Check `externalDependencies` in angular.json — native modules like `canvas` must be external |
| TransferState issues | Check `@ngx-translate` compatibility with server/browser loader pattern |
| XHR factory errors | `ServerXhr` wraps `xhr2` — check xhr2 compatibility |

## Native Federation Build Errors

Applies only to federated apps (see `references/native-federation.md`).

| Error Pattern | Auto-Fix Strategy |
|---------------|-------------------|
| Config not found / `Cannot find module './federation.config.js'` after v4 bump | v4 renamed the config to `federation.config.mjs` (ESM). Rename it, convert `require`/`module.exports` → `import`/`export default`, and update the `angular.json` builder options that reference it |
| `require is not defined` / `module is not defined` in `federation.config` | Same v3→v4 CommonJS→ESM issue — convert the config to ESM (`.mjs`, `export default`) |
| Stale/incorrect chunks or `Cannot find remoteEntry` right after a v4 bump | Wipe caches and rebuild: `rm -rf dist .angular node_modules/.cache` (required on the v3→v4 boundary) |
| `initFederation` / import errors from `@angular-architects/native-federation` | Wrong adapter package for the target major (`native-federation` vs `native-federation-v4` vs `@22.x`) — install the correct one per the table in `references/native-federation.md` |
| Shared-dependency / singleton version-mismatch warnings at build or bootstrap | Reconcile `shareAll()`/`share()` versions; ensure singletons match across host + remotes (lockstep). Not fixable in one repo alone |
| esbuild plugin failure from the native-federation builder | Adapter/Angular major mismatch — the adapter must match the just-installed Angular major |
| `FsPath: .../src/src/main.ts does not exist` after an NF **v20** `ng update` | v20 (v3 adapter) derives the entry point from the tsConfig directory; a `src/`-nested `tsconfig.app.json` yields `src/src/main.ts`. Move `tsconfig.app.json` to the workspace root — see "Angular 20 build layout" in `references/native-federation.md` |
| `Expected .../federation.config.js` (NF v20) | The builder expects `federation.config.js` as a **sibling of the tsConfig**; move it to the root alongside `tsconfig.app.json` — same reference |
| `invalid path mapping detected: @angular/*: ../node_modules/@angular/*` (after moving tsConfig to root) | The base-tsconfig `@angular/*` path mapping was calibrated for the old `src/` depth; **delete it** (Angular resolves via `node_modules`) and set the moved app tsconfig `baseUrl: "src"` — same reference |
| Build fails at the **prerender / SSG** step with a remote unreachable | Federated prerender needs remotes reachable at build time — point `federation.manifest.json` at published/running remotes, or exclude federated routes from prerender |
| Remotes don't load at runtime with an import-map / `es-module-shims` error (no build error) | Bump `es-module-shims` (pinned in `index.html` / `package.json`); ensure CSP `script-src`/`connect-src` allow the remote origins and the nonce covers the import-map + es-module-shims tags — see `references/native-federation.md` |

## Angular 21 Specific: `@Input()` Type Errors

Angular 21 enforces stricter checks. These appear as build errors in component templates.

### Pattern 1 — `@Input()` inferred as `null` type

Component has `@Input() member = null` (no explicit type). Angular 21 infers as literal `null`. Template access `member.property` (no `?.`) is rejected.

```typescript
// Before (rejected in Angular 21)
@Input() member = null;

// After
@Input() member: any = null;

// For typed inputs:
@Input() details: DetailModel | null = null;
```

### Pattern 2 — Implicit `any` on method parameters

```typescript
// Before
handleSelection(selectedInfo) { ... }

// After
handleSelection(selectedInfo: any) { ... }
```

## Fix Rules

- **DO fix**: anything that causes a compile error or build failure
- **DO NOT touch**: code that still compiles and works, even if a newer preferred style exists
