# Reduction pattern catalog

Each pattern has: how to detect it, what it typically saves, its risk, the recipe, and the check
that proves it landed. Estimates rank candidates. Only a metafile delta closes one.

Apply one pattern per commit.

## Contents

| Pattern | Typical saving | Risk |
| --- | --- | --- |
| [P1 — Eager side-effect registration in `main.ts`](#p1--eager-side-effect-registration-in-maints) | the library's full size | low |
| [P2 — Eager `importProvidersFrom` in the app config](#p2--eager-importprovidersfrom-in-the-app-config) | 20–150 KB | medium |
| [P3 — Static imports of feature internals in the root routes file](#p3--static-imports-of-feature-internals-in-the-root-routes-file) | large, usually underestimated | medium |
| [P4 — Always-on shell UI](#p4--always-on-shell-ui) | large but diffuse | medium-high (SSR) |
| [P5 — Entry-point and barrel hygiene](#p5--entry-point-and-barrel-hygiene) | small each, adds up | low |
| [P6 — Crypto, date and UA libraries](#p6--crypto-date-and-ua-libraries) | 70–230 KB | medium |
| [Anti-patterns — do not do these](#anti-patterns--do-not-do-these) | — | — |

---

## P1 — Eager side-effect registration in `main.ts`

**Detect.** Read `src/main.ts` top to bottom. Look for imports whose only purpose is a side effect
executed at bootstrap: `register()`, `defineCustomElements()`, `registerLocaleData`, monkey-patch
shims, analytics SDK init. Then count real consumers:

```bash
grep -rl "<custom-element-tag>" src --include="*.html"
grep -rn "<library-name>" src --include="*.ts"
```

If consumers live only under lazy routes, the whole library is eager for nothing.

**Saving.** The library's full size. Frequently the single largest one-change win in the repo —
web-component wrappers ship every module in one file (Swiper's `element/bundle` is ~180 KB raw).

**Risk.** Low, if registration is awaited before the element is configured.

**Recipe.** A shared idempotent, browser-only loader:

```ts
// src/app/utils/<lib>-loader.ts
let pending: Promise<void> | null = null;

export function loadLibElement(): Promise<void> {
  if (typeof customElements === 'undefined') return Promise.resolve(); // SSR: no custom elements
  pending ??= import('<lib>/element/bundle').then(({ register }) => register());
  return pending;
}
```

Delete the eager import and call from `main.ts`. In each consumer, await the loader before
touching the element:

```ts
ngAfterViewInit() {
  if (this.utilityService.isBrowser()) {
    void loadLibElement().then(() => this.initializeCarousel());
  }
}
```

**Why this is safe.** `customElements.define()` upgrades elements already in the DOM, so markup
parsed (or server-rendered) before registration still becomes a live component. It is only the
imperative calls — `Object.assign(el, config); el.initialize()` — that must wait, because
`initialize` does not exist until the element is defined.

**Two traps.**

- Consumers that *don't* call `initialize()` (no `init="false"` on the tag) still need the loader
  called, or the element never upgrades. Auto-init consumers need `void loadLibElement()` with no
  `.then()`.
- The `pending ??=` memo must be module-scoped, not per-component, or every instance triggers its
  own dynamic import and the chunk is fetched repeatedly.

**Check.** The package is absent from the eager package table; a new lazy chunk containing it
appears; eager JS drops by roughly the library's size; total JS is roughly flat.

---

## P2 — Eager `importProvidersFrom` in the app config

**Detect.** `app.config.ts` / `app.provider.config.ts`: every `forRoot()` inside
`importProvidersFrom(...)` is instantiated at bootstrap and its module graph is eager.

**Saving.** Varies, 20–150 KB. Chat SDKs, map modules and date adapters are the usual offenders.

**Risk.** Medium — a provider moved to a route is no longer injectable outside it.

**Recipe.** Move the `forRoot()` into the `providers` of the routes that actually need it (Angular
supports route-level `providers` with `importProvidersFrom`). Where the module is genuinely global
but heavy, keep the token eager and lazy-load the implementation behind it.

Also check for framework-level swaps that are pure wins:

- `BrowserAnimationsModule` → `provideAnimationsAsync()`, which lazy-loads the animation engine.
- `importProvidersFrom(SomeModule.forRoot())` → the library's `provideSomething()` function when
  one exists; the functional form tree-shakes and the NgModule form does not.

**Check.** The package leaves the eager set. Then smoke-test every route that injects it — a
missing provider is a runtime `NullInjectorError`, invisible to the build.

---

## P3 — Static imports of feature internals in the root routes file

**Detect.** The import block at the top of `root-routes.ts` / `app.routes.ts`. Anything imported
from `./modules/**` is eager, *regardless* of the route below it using `loadComponent` or
`loadChildren`. Guards, resolvers, feature services and i18n loader factories are the usual cargo.

**Saving.** Often large and always underestimated, because one guard drags its service, which
drags its models and HTTP layer.

**Risk.** Medium — guard semantics change if converted carelessly.

**Recipe.**

- Class guards → functional guards defined in the feature, referenced lazily:
  ```ts
  canActivate: [() => import('./modules/x/x.guard').then((m) => m.xGuard)]
  ```
  (or keep the guard class but move it to a file that imports nothing from the feature).
- i18n loader factories → move into the lazily-loaded route's own `providers`.
- Route-level `providers: [FeatureService]` → move into the feature's routes file, loaded with it.

**Check.** `src (app code)` shrinks in the eager package table and the feature's chunk grows.

---

## P4 — Always-on shell UI

**Detect.** The root component's template. Footer, mega-menu, cookie banner, login/SSO modal,
upgrade notification, floating cart — rendered on every route, needed on almost none of them
immediately. These transitively pull the design-system packages into the eager set.

**Saving.** Large but diffuse; depends on how much of the design system each pulls.

**Risk.** Medium-high on SSR. This is the one pattern that changes rendered DOM.

**Recipe.** `@defer` with the right trigger:

```html
@defer (on viewport) { <app-footer /> } @placeholder { <div class="footer-skeleton"></div> }
@defer (on interaction) { <app-login-modal /> } @placeholder { <button>Masuk</button> }
```

Never `@defer` above-the-fold content — it costs LCP, which is worse than the bytes.

**Do not** "fix" this by deep-importing a library's unexported internal paths — it breaks the
package contract. Run the shake probe (`analyze-deps.mjs`) first. If the library shakes, deferring
the component is the fix. If it does not (one chunk module behind the barrel, 90–100% retained),
the fix is a published secondary entry point upstream, then switching the app to that subpath.

**Check.** Eager JS down; SSR HTML for an affected route diffed and reviewed; LCP not regressed.

---

## P5 — Entry-point and barrel hygiene

**Detect.** `import { MatDialogModule } from '@angular/material'` (barrel) instead of
`'@angular/material/dialog'`. Similarly for icon sets and utility libraries.

**Saving.** Small per instance; adds up.

**Risk.** Low.

**Recipe.** Import from the narrowest published entry point. Push dialog- and bottom-sheet-heavy
flows into lazy routes.

**Check.** Package raw bytes drop in the eager table.

---

## P6 — Crypto, date and UA libraries

**Detect.** `crypto-js`, `moment`, `luxon`, `ua-parser-js` in the eager package table. Find who
pulls them:

```bash
<PM> why crypto-js
grep -rn "crypto-js\|ua-parser" src --include="*.ts"
```

**Saving.** `crypto-js` ~70 KB, `moment` ~230 KB (+locales).

**Risk.** Medium — often transitive through an internal library, so the fix belongs upstream.

**Recipe.** Prefer the platform: `crypto.subtle` for hashing, `Intl.DateTimeFormat` for
formatting, `navigator.userAgentData` where the check allows it. When the dependency is transitive
through a `@web-shared/*` or `@your-org/*` package, raise it with that package's owners — patching the
consumer does not remove the bytes.

**Check.** Package leaves the eager set; behaviour verified for hashing/formatting parity.

---

## Anti-patterns — do not do these

| Tempting | Why not |
| --- | --- |
| Deep-importing a library's unexported internals | Breaks the package contract; if the barrel does not shake, add a secondary entry point upstream instead |
| Reporting `main-*.js` alone | Understates first load; hides code merely moved between eager chunks |
| Batching several changes into one commit | A regression cannot be attributed or reverted cleanly |
| `@defer` on above-the-fold content | Trades bytes for LCP — a net loss |
| Claiming an estimate as a result | Estimates rank; metafiles prove |
| Dropping `--max-old-space-size` from the build command | Produces an OOM, not a smaller bundle |
