# Zoneless API Reference

## Providers

### `provideZonelessChangeDetection()` (Angular 19+, stable)

```typescript
import { provideZonelessChangeDetection } from '@angular/core';
```

Use in `AppModule.providers[]` (NgModule) or `bootstrapApplication` providers (standalone).

### `provideExperimentalZonelessChangeDetection()` (Angular 18 only)

Deprecated in favour of the stable API above. Do NOT use for Angular 19+.

---

## Change Detection Strategy

### `ChangeDetectionStrategy.OnPush`

```typescript
import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
})
```

Required for every component in a zoneless app. Without it, Angular may still
work but loses the performance benefits and predictability of zoneless CD.

---

## Signals API

### `signal<T>(initialValue)`

```typescript
import { signal } from '@angular/core';

count = signal(0);

// Update
this.count.set(1);
this.count.update(v => v + 1);

// Read (in template or TS)
this.count();
```

### `computed<T>(fn)`

```typescript
import { computed } from '@angular/core';

doubled = computed(() => this.count() * 2);
```

### `effect(fn)`

```typescript
import { effect, inject, DestroyRef } from '@angular/core';

constructor() {
  effect(() => {
    console.log('count changed:', this.count());
  });
}
```

### `toSignal(observable$)`

```typescript
import { toSignal } from '@angular/core/rxjs-interop';

data = toSignal(this.service.data$, { initialValue: [] });
```

### `toObservable(signal)`

```typescript
import { toObservable } from '@angular/core/rxjs-interop';

data$ = toObservable(this.dataSignal);
```

---

## ChangeDetectorRef (limited use in zoneless)

In zoneless apps, prefer signals. But if `ChangeDetectorRef` is still used:

| Method | Zoneless behaviour |
|---|---|
| `markForCheck()` | Schedules component for next CD cycle. OK to use. |
| `detectChanges()` | Runs CD synchronously. Use sparingly — prefer signals. |
| `detach()` | Detaches component from CD tree. Works in zoneless. |
| `reattach()` | Reattaches. Works in zoneless. |

---

## NgZone in Zoneless

`NgZone` still exists as a DI token in zoneless apps, but `NgZone.run()` does
nothing useful — there is no zone to run in. Remove all `NgZone.run()` calls
and replace with direct signal updates.

```typescript
// REMOVE
constructor(private ngZone: NgZone) {}
this.ngZone.run(() => this.value = 42);

// REPLACE WITH
value = signal(0);
this.value.set(42);
```

---

## ApplicationRef

`ApplicationRef.tick()` triggers a global CD cycle. In zoneless apps, this is
replaced by automatic scheduling from signals. Remove calls to `ApplicationRef.tick()`
unless you have a very specific reason to trigger a manual global cycle.

---

## Router and HTTP (no changes needed)

Angular Router and `HttpClient` are already zoneless-compatible. They schedule
change detection via `ChangeDetectorRef.markForCheck()` internally. No migration
needed for these.

---

## Async Pipe

`async` pipe still works in zoneless — it calls `markForCheck()` internally.
However, prefer `toSignal()` + signal binding in new code for performance.

```html
<!-- Still works in zoneless -->
{{ data$ | async }}

<!-- Preferred in zoneless -->
{{ data() }}
```
