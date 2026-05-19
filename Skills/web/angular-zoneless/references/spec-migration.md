# Spec File Migration Guide

## TestBed Configuration

Add `provideZonelessChangeDetection()` to every test module that tests zoneless components.

```typescript
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

beforeEach(async () => {
  await TestBed.configureTestingModule({
    declarations: [MyComponent],
    providers: [
      provideZonelessChangeDetection(),
      // ...other providers
    ],
  }).compileComponents();

  fixture = TestBed.createComponent(MyComponent);
  fixture.detectChanges(); // initial render
});
```

For service-only tests (no component), you still benefit from adding it to prevent
zone-related errors if the service uses signals or interacts with components.

---

## `fakeAsync` / `tick` → `async` / `await`

This is the most common change in spec files.

### Simple async operation

```typescript
// BEFORE
it('loads data', fakeAsync(() => {
  component.loadData();
  tick(100);
  fixture.detectChanges();
  expect(component.items.length).toBe(3);
}));

// AFTER
it('loads data', async () => {
  component.loadData();
  await fixture.whenStable();
  fixture.detectChanges();
  expect(component.items().length).toBe(3);
});
```

### setTimeout / timer

```typescript
// BEFORE
it('shows toast after delay', fakeAsync(() => {
  component.showToast();
  tick(3000);
  expect(component.toastVisible).toBe(false);
}));

// AFTER
it('shows toast after delay', async () => {
  component.showToast();
  await new Promise(r => setTimeout(r, 3000));
  fixture.detectChanges();
  expect(component.toastVisible()).toBe(false);
});
```

### HTTP / Observable

```typescript
// BEFORE
it('fetches user', fakeAsync(() => {
  service.getUser(1).subscribe(u => (result = u));
  tick();
  expect(result.name).toBe('Alice');
}));

// AFTER
it('fetches user', async () => {
  const result = await firstValueFrom(service.getUser(1));
  expect(result.name).toBe('Alice');
});
```

---

## `flushMicrotasks` → `await Promise.resolve()`

```typescript
// BEFORE
flushMicrotasks();

// AFTER
await Promise.resolve();
```

---

## `fixture.detectChanges()` — still required

In zoneless tests, Angular does NOT automatically trigger change detection.
You must call `fixture.detectChanges()` after every state mutation that
should be reflected in the DOM.

```typescript
it('updates DOM on signal change', async () => {
  component.label.set('Updated');
  fixture.detectChanges(); // required
  expect(fixture.nativeElement.querySelector('h1').textContent).toBe('Updated');
});
```

Use `await fixture.whenStable()` before `detectChanges()` when waiting for
async operations (HTTP, timers, promises) to complete.

---

## Removing `NgZone` from Tests

```typescript
// BEFORE — injecting NgZone to wrap async operations
let ngZone: NgZone;
beforeEach(() => {
  ngZone = TestBed.inject(NgZone);
});
it('runs outside zone', () => {
  ngZone.runOutsideAngular(() => component.doWork());
});

// AFTER — NgZone is irrelevant in zoneless; remove injection and wrapping
it('runs work', () => {
  component.doWork();
});
```

---

## Signal-based Assertions

If components now use signals instead of plain properties:

```typescript
// BEFORE (zone-based, plain property)
expect(component.count).toBe(5);

// AFTER (zoneless, signal)
expect(component.count()).toBe(5);
```

---

## Karma Config — Remove Zone.js Testing Import

In `src/test.ts` or `karma.conf.js` setup file:

```typescript
// REMOVE this line:
import 'zone.js/testing';
```

If `zone.js` is imported in `polyfills.ts`, remove it from there too.

---

## Global TestBed Helper

For large projects, create a shared helper to avoid repeating the zoneless provider:

```typescript
// src/testing/setup-zoneless.ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';

export function setupZonelessTestBed(config: Parameters<typeof TestBed.configureTestingModule>[0]) {
  return TestBed.configureTestingModule({
    ...config,
    providers: [
      provideZonelessChangeDetection(),
      ...(config.providers ?? []),
    ],
  });
}
```

Usage:

```typescript
beforeEach(async () => {
  await setupZonelessTestBed({
    declarations: [MyComponent],
  }).compileComponents();
});
```

---

## Common Test Failures After Migration

| Error | Cause | Fix |
|---|---|---|
| `No NgZone provided` | Zone.js removed but something injected NgZone | Remove `NgZone` injection or provide `NgZone` stub |
| Template not updating | Missing `fixture.detectChanges()` | Add call after state change |
| `fakeAsync` import error | `zone.js/testing` removed | Switch to `async`/`await` |
| `tick()` undefined | Zone.js testing removed | Replace with `await` pattern |
| Test hangs on async | Using real timers without awaiting | Use `await fixture.whenStable()` |
