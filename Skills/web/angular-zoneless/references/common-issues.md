# Common Issues & Fixes

## 1. Component not updating in UI

**Symptom:** Signal updates don't reflect in the DOM.

**Cause:** Component missing `ChangeDetectionStrategy.OnPush`.

**Fix:**
```typescript
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
})
```

---

## 2. `ExpressionChangedAfterItHasBeenCheckedError`

**Symptom:** Error thrown in development during change detection.

**Cause:** State updated during the CD cycle itself (e.g., in `ngAfterViewChecked`).

**Fix:** Move state updates to `ngOnInit`, `effect()`, or event handlers.
Avoid updating signals in lifecycle hooks that run during CD.

---

## 3. `NgZone is not provided` / Zone injection errors

**Symptom:** DI error at runtime or in tests.

**Cause:** Some third-party library or legacy code injects `NgZone` expecting it to exist.

**Fix:**
- For your own code: remove `NgZone` injection, use signals instead.
- For third-party: provide a mock `NgZone`:
  ```typescript
  providers: [{ provide: NgZone, useClass: NoopNgZone }]
  ```
- `NoopNgZone` is available from `@angular/core`.

---

## 4. `fakeAsync` test errors after removing `zone.js/testing`

**Symptom:** `Error: fakeAsync is not in a task` or import errors.

**Cause:** `fakeAsync` relies on Zone.js patching timers. Without `zone.js/testing`, it breaks.

**Fix:** Replace all `fakeAsync` + `tick()` with `async`/`await`. See `spec-migration.md`.

---

## 5. `async` pipe stops updating

**Symptom:** Observable bound with `async` pipe doesn't update UI.

**Cause:** Without Zone.js, the `async` pipe calls `markForCheck()` but without `OnPush`
on the component, this does nothing.

**Fix:** Add `ChangeDetectionStrategy.OnPush` to the component.

---

## 6. RxJS subscriptions not triggering CD

**Symptom:** Observable emits value, component property updated, but UI not refreshed.

**Cause:** Zone.js used to intercept async operations and trigger CD. Zoneless doesn't.

**Fix:** Use `toSignal()` to convert observables to signals, or call `this.cdr.markForCheck()`
inside the subscription:
```typescript
this.service.data$.pipe(
  takeUntilDestroyed(this.destroyRef)
).subscribe(data => {
  this.data.set(data); // signal update triggers CD
});
```

---

## 7. `setTimeout` / `setInterval` not triggering CD

**Symptom:** Callback runs, value updated, UI stale.

**Cause:** Zone.js patched timers to trigger CD. Zoneless doesn't.

**Fix:** Update a signal inside the timer callback:
```typescript
setTimeout(() => {
  this.counter.set(this.counter() + 1); // signal update schedules CD
}, 1000);
```

---

## 8. Third-party library uses `NgZone.run()`

**Symptom:** Library triggers UI updates that stop working after migration.

**Cause:** Library calls `NgZone.run()` which is a no-op in zoneless.

**Fix:**
- If library exposes a callback/event, subscribe and update a signal from there.
- File an issue with the library for zoneless compatibility.
- As a workaround, intercept the library's output and pipe through a signal.

---

## 9. `ChangeDetectorRef.detectChanges()` called in production code

**Symptom:** Works in Zone.js but causes issues in zoneless (double renders or no-ops).

**Cause:** Legacy pattern from zone-based CD.

**Fix:**
- Prefer signals: remove `detectChanges()` entirely if state is signal-driven.
- If absolutely needed: replace with `markForCheck()`.

---

## 10. Tests pass in isolation but fail together

**Symptom:** Spec file works alone but fails when run with other specs.

**Cause:** Shared state or `provideZonelessChangeDetection()` not isolated per `TestBed`.

**Fix:** Ensure each `beforeEach` calls `TestBed.resetTestingModule()` or uses
`TestBed.configureTestingModule` fresh. Angular's test runner does this by default —
check for `TestBed.overrideComponent` or static providers leaking state.

---

## 11. NgModule app — `provideZonelessChangeDetection()` not recognized

**Symptom:** Type error or runtime error on `AppModule.providers`.

**Cause:** Importing from wrong location or wrong Angular version.

**Fix:** Ensure Angular 19+ and import from `@angular/core`:
```typescript
import { provideZonelessChangeDetection } from '@angular/core';
```
For Angular 18, use `provideExperimentalZonelessChangeDetection` from `@angular/core`.

---

## 12. `bootstrapModule` vs `bootstrapApplication`

**Symptom:** NgModule app migration path unclear.

**Clarification:**
- `bootstrapModule(AppModule)` → add `provideZonelessChangeDetection()` to `AppModule.providers`
- `bootstrapApplication(AppComponent, config)` → add to `config.providers`
- Both approaches are valid for zoneless; no need to convert to standalone first.
