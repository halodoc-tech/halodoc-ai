# Error Patterns

Use this file for quick source mapping, root-cause framing, and fix-shape hints for common Angular application failures.

Prefer fixes that restore the intended contract or lifecycle. Do not treat optional chaining, `ngSkipHydration`, or global error logging as the real fix unless the value or workaround is valid by design.

## Contents

- [Null / undefined property access](#null--undefined-property-access)
- [Input contract and lifecycle ordering](#input-contract-and-lifecycle-ordering)
- [SSR / browser-only failures](#ssr--browser-only-failures)
- [Hydration mismatch and direct DOM manipulation](#hydration-mismatch-and-direct-dom-manipulation)
- [Unhandled async errors and callsite handling](#unhandled-async-errors-and-callsite-handling)
- [Subscription / lifecycle leakage](#subscription--lifecycle-leakage)
- [Collection tracking and list identity](#collection-tracking-and-list-identity)
- [Template diagnostic patterns](#template-diagnostic-patterns-that-often-become-runtime-bugs)
- [Forms and control wiring issues](#forms-and-control-wiring-issues)
- [Dependency injection and provider contract issues](#dependency-injection-and-provider-contract-issues)
- [Change-detection and expression-stability problems](#change-detection-and-expression-stability-problems)
- [Source mapping prompts](#source-mapping-prompts)
- [Audit prompts](#audit-prompts)

## Null / undefined property access

Signals:
- `Cannot read properties of undefined`
- Safari phrasing like `undefined is not an object`
- property names map directly to a component field, input, or API payload shape

Likely causes:
- render guard checks one state source while template dereferences another
- `ngOnChanges` assumes a `SimpleChange` entry exists
- async population happens after template visibility flips on
- service response shape differs from assumed contract

Preferred fixes:
- restore the state/render contract
- align visibility checks with the actual rendered data source
- initialize the state that the template reads from
- guard `SimpleChange` presence only when the change is legitimately optional

## Input contract and lifecycle ordering

Signals:
- failures around `currentValue`, `previousValue`, `firstChange`
- crashes during `ngOnChanges`, `ngOnInit`, or immediately after input changes
- child component assumes parent always passes data synchronously

Likely causes:
- parent/child input contract is underspecified
- component reads dependent state before the input-derived state is ready
- initialization happens in the wrong lifecycle phase

Preferred fixes:
- align parent and child contracts
- initialize derived state before rendering depends on it
- move logic to the lifecycle phase where the dependency is guaranteed
- guard only the truly optional input/change paths

## SSR / browser-only failures

Signals:
- failures around `window`, `document`, `navigator`, `location`, `localStorage`, `matchMedia`
- issue occurs on initial load, SSR render, or hydration but not after client-only navigation
- stack includes server render or hydration frames

Likely causes:
- browser APIs are accessed during SSR
- DOM-dependent code runs before the browser-only phase
- third-party scripts assume browser globals too early

Preferred fixes:
- `isPlatformBrowser`
- defer DOM access until browser-only lifecycle
- provide SSR-safe fallback state

## Hydration mismatch and direct DOM manipulation

Common Angular signals:
- `NG0500` hydration node mismatch
- `NG0503` unsupported projection of DOM nodes
- `NG0507` HTML altered after SSR

Likely causes:
- direct DOM manipulation with native APIs changes the server-rendered structure
- `innerHTML` or `outerHTML` mutates hydrated DOM
- HTML is post-processed by CDN/build steps in a way that strips Angular markers, whitespace, or comments
- content projection uses nodes created outside Angular context

Angular-recommended direction:
- prefer Angular rendering APIs over native DOM mutation
- keep the SSR HTML structurally identical until hydration completes
- use `ngSkipHydration` only as a last-resort workaround, not as the default fix

Preferred fixes:
- replace native DOM creation/mutation with Angular template or view APIs
- stop CDN or post-processing steps from rewriting SSR HTML
- isolate the component and use `ngSkipHydration` only when the component cannot yet be made hydration-safe
- never introduce `innerHTML`/`outerHTML` assignment of unsanitized dynamic content while fixing this — a fix here must go through Angular's `DomSanitizer` or template binding, never raw string interpolation into the DOM

## Unhandled async errors and callsite handling

Signals:
- errors reach global `ErrorHandler`
- errors originate from API calls, promises, or observables kicked off by app code
- logs show global exception reporting with little operation context

Likely causes:
- the callsite does not handle the async failure
- error handling is deferred to a global handler instead of the operation that initiated the work
- observable/promise failures are treated as fatal when they should update UI state

Angular-recommended direction:
- handle errors at the callsite whenever possible
- use `catchError`, `try/catch`, or explicit UI error states for recoverable failures
- treat global `ErrorHandler` as reporting infrastructure, not business recovery logic

Preferred fixes:
- add `catchError` or explicit promise handling where the request starts
- map recoverable failures into UI state instead of throwing through the app
- keep global error handling for unexpected or fatal failures

## Subscription / lifecycle leakage

Signals:
- repeated errors over time
- post-navigation crashes
- destroyed components still handling streams, polling, timers, or callbacks

Likely causes:
- subscriptions outlive the component
- polling/interval logic is not stopped in destroy
- side effects continue after navigation

Preferred fixes:
- `takeUntil(this.ngUnsubscribe$)`
- unsubscribe polling/subscriptions in `ngOnDestroy`
- cancel timers or callbacks tied to component lifetime

## Collection tracking and list identity

Common Angular signals:
- `NG0955` duplicated keys in `@for`
- `NG0956` tracking expression re-creates the DOM structure

Likely causes:
- tracking by object identity instead of stable key
- duplicate keys in repeated collections
- immutable updates recreate objects and the track expression is not stable

Angular-recommended direction:
- track by a stable unique identifier such as `item.id`
- avoid `track item` when immutable updates replace object identity

Preferred fixes:
- switch to `track item.id` or another stable unique key
- ensure the key is unique across the collection
- verify focus/input/iframe state is preserved after updates

## Template diagnostic patterns that often become runtime bugs

Relevant Angular diagnostics:
- `NG8102` nullish coalescing on non-nullable value
- `NG8107` optional chain on non-nullable value
- `NG8109` interpolated signal not invoked

Likely causes:
- the type model and runtime model disagree
- template assumes a signal/value shape incorrectly
- defensive syntax is masking a deeper state-model issue

Preferred fixes:
- align runtime optionality with actual types
- invoke signals correctly in templates
- remove fake optionality and fix the underlying invariant

## Forms and control wiring issues

Common Angular runtime classes:
- missing control or path errors
- control value accessor wiring failures
- template and form model drift after conditional rendering

Likely causes:
- form control path does not match template structure
- conditional UI removes controls the form still expects
- custom control does not satisfy the Angular forms contract

Preferred fixes:
- align control names/paths with the real form shape
- create/remove controls in sync with conditional UI
- verify custom inputs implement the control contract correctly

## Dependency injection and provider contract issues

Common Angular runtime classes:
- missing provider / invalid injection context failures
- feature-level provider duplication or unexpected scope

Likely causes:
- provider registered in the wrong injector scope
- `inject()` used outside a valid injection context
- standalone/feature provider boundaries are misconfigured

Preferred fixes:
- move shared providers to the correct scope
- use `inject()` only in valid contexts such as field initializers/providers/factories
- verify feature and root provider ownership

## Change-detection and expression-stability problems

Common Angular runtime classes:
- expression changed after checked
- state mutates during render or immediately after checked bindings

Likely causes:
- synchronous mutation in template-driven lifecycle flow
- state is updated in a hook that runs too late for the bound value
- component mixes derived and source state in a way that breaks render stability

Preferred fixes:
- move mutation earlier or later so the value is stable during render
- derive state in a single place instead of mutating from multiple hooks
- avoid patching the symptom with manual detection unless the lifecycle reasoning is sound

## Source mapping prompts

When stack traces point to minified `<your-domain>/resources/*.js` bundles:
- combine chunk/page/property signals first
- then use the S3 sourcemap workflow from `references/sourcemaps.md`
- do not claim high source confidence from vendor/minified frames alone

## Audit prompts

After a fix, ask:
- does a sibling component use the same lifecycle or render contract?
- does the same module gate UI from raw payload but render from derived state?
- is the same property accessed in both HTML and TS through different sources?
- is the same pattern likely to fail under SSR, hydration, or immutable list updates?
