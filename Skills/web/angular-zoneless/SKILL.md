---
name: angular-zoneless
description: >
  Migrate Angular applications from Zone.js to zoneless change detection.
  Use this skill when the user wants to: migrate to zoneless, remove Zone.js,
  adopt signal-based reactivity, update ChangeDetectionStrategy, fix spec files
  for zoneless, or asks about provideZonelessChangeDetection. Also triggers for:
  "migrate to zoneless", "remove zone.js", "zoneless Angular",
  "signal-based change detection", "OnPush migration", "fakeAsync to async",
  "convert to signals", "update to Angular signals", "remove NgZone",
  "fix TestBed for zoneless".
  Always use this skill for any Angular zoneless migration task, even partial ones.
---

# Angular Zoneless Migration

Migrate Angular apps from Zone.js-based to zoneless change detection.

Arguments via `$ARGUMENTS`: `[component|spec|config|all] [--dry-run]`

- `component` → only Phase 2
- `spec` → only Phase 3
- `config` → only Phase 1 + 4
- `all` or empty → full migration
- `--dry-run` → preview changes without editing files (see Dry-Run Mode below)

## Quick Start

Run analysis first, then migrate in phases:

```bash
bash <skill-path>/scripts/analyze-zone-usage.sh
bash <skill-path>/scripts/find-cd-patterns.sh
```

> `<skill-path>` is the directory containing this skill. Find it with:
> `find ~/.claude -path "*/angular-zoneless/scripts" -type d 2>/dev/null | head -1`

---

## Safety Checkpoint

**Before any file edits**, ensure the user is on a dedicated branch:

```bash
# Adjust branch name to team conventions (feat/, chore/, etc.):
git checkout -b zoneless-migration
# or if already on a feature branch:
git status
```

If uncommitted changes exist, prompt the user to commit or stash first. This ensures a clean recovery path if anything goes wrong mid-migration.

---

## Dry-Run Mode

When `$ARGUMENTS` contains `--dry-run`:

1. Run both analysis scripts to generate the baseline report (read-only — scripts do not modify files).
2. For each phase in scope, **list** the files that would be changed and what change would be made. Example output:

```
[DRY RUN] Phase 1: Would add provideZonelessChangeDetection() to src/app/app.module.ts
[DRY RUN] Phase 2: 14 components missing ChangeDetectionStrategy.OnPush (see report)
[DRY RUN] Phase 3: 7 spec files use fakeAsync — would convert to async/await
[DRY RUN] Phase 4: Would remove 'zone.js' from polyfills.ts and angular.json
```

3. Do **NOT** edit any files. Ask the user to rerun without `--dry-run` to apply changes.

---

## Phase 1 — Bootstrap Config

### Before Phase 1 — Detect Angular version

Read `package.json` and extract the `@angular/core` version:

```bash
node -e "const p=require('./package.json'); console.log(p.dependencies['@angular/core'] || p.devDependencies['@angular/core'])"
```

> Output is a semver range (e.g., `^19.0.0`, `~18.2.0`). Use the major version only: `^19.x.x` → 19.x, `~18.x.x` → 18.x.

| Angular version | Provider to use | Action |
|---|---|---|
| 19.x or later | `provideZonelessChangeDetection()` | Use all Phase 1 examples as written |
| 18.x | `provideExperimentalZonelessChangeDetection()` | Substitute in all Phase 1 examples |
| < 18 | Not supported | Stop. Tell user: "Angular zoneless requires 18+. Your version is X." |

Use the correct provider throughout **all phases** (Phase 1, Phase 3 TestBed templates).

### NgModule-based apps (`AppModule`)

```typescript
// app.module.ts
import { provideZonelessChangeDetection } from '@angular/core';

@NgModule({
  providers: [
    provideZonelessChangeDetection(),
    // ...existing providers
  ],
})
export class AppModule {}
```

### Standalone apps (`bootstrapApplication`)

```typescript
// main.ts
import { provideZonelessChangeDetection } from '@angular/core';

bootstrapApplication(AppComponent, {
  providers: [
    provideZonelessChangeDetection(),
  ],
}).catch(console.error);
```

---

## Phase 2 — Component Migration

Every component **must** have `ChangeDetectionStrategy.OnPush`. Without it, zoneless
change detection silently falls back or misses updates.

### Checklist per component

1. Add `changeDetection: ChangeDetectionStrategy.OnPush` to `@Component` decorator
2. Replace mutable state with Angular Signals (`signal()`, `computed()`, `effect()`)
3. Replace `NgZone.run(fn)` with direct signal updates — Zone no longer exists
4. Replace `ChangeDetectorRef.detectChanges()` with `markForCheck()` or signals
5. Replace `ApplicationRef.tick()` calls — use signals to drive updates

### Before → After patterns

```typescript
// BEFORE: zone-driven mutation
this.items = [...newItems];

// AFTER: signal-driven
this.items = signal([...newItems]);
// in template: {{ items() }}
```

```typescript
// BEFORE: NgZone.run for async callback
this.ngZone.run(() => {
  this.data = result;
  this.cdr.detectChanges();
});

// AFTER: signal update (no zone needed)
this.data.set(result);
```

```typescript
// BEFORE: detectChanges
this.cdr.detectChanges();

// AFTER: markForCheck (or preferably use signals)
this.cdr.markForCheck();
```

### Component decorator diff

```typescript
// BEFORE
@Component({
  selector: 'app-my',
  templateUrl: './my.component.html',
})

// AFTER
@Component({
  selector: 'app-my',
  templateUrl: './my.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
```

> For large codebases, use the script `<skill-path>/scripts/find-cd-patterns.sh` to list
> all components missing `OnPush` before editing manually.

---

## Phase 3 — Spec File Migration

Read `references/spec-migration.md` for full patterns and examples.

### Summary of changes

| Before (Zone.js) | After (Zoneless) |
|---|---|
| `fakeAsync(() => { ... tick() })` | `async () => { await ... }` |
| `flushMicrotasks()` | `await Promise.resolve()` |
| `tick(ms)` | `await new Promise(r => setTimeout(r, ms))` |
| TestBed has no zoneless provider | Add `provideZonelessChangeDetection()` |
| Zone handles CD automatically | Call `fixture.detectChanges()` explicitly |
| `NgZone` injection for zone wrapping | Remove — not needed in zoneless |

### TestBed template

```typescript
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

describe('MyComponent', () => {
  let fixture: ComponentFixture<MyComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [MyComponent],
      providers: [
        provideZonelessChangeDetection(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(MyComponent);
    fixture.detectChanges();
  });
});
```

---

## Phase 4 — Cleanup

### Remove Zone.js from polyfills

```typescript
// polyfills.ts — remove this line:
import 'zone.js';
```

### Remove Zone.js from test polyfills

```typescript
// test.ts or karma setup — remove:
import 'zone.js/testing';
```

### angular.json

Remove `zone.js` from `polyfills` array if listed explicitly:

```json
// BEFORE
"polyfills": ["zone.js"]

// AFTER
"polyfills": []
```

### package.json (optional, after full removal)

```bash
pnpm remove zone.js
```

Only do this after confirming nothing else depends on Zone.js.

---

## Migration Complete

After Phase 4, run the following to verify the migration produced a working build:

```bash
ng build
ng test
```

Migration is complete when **all** of the following are true:

- `ng build` succeeds with no errors
- `ng test` passes (or any remaining failures are pre-existing and unrelated)
- Re-running both analysis scripts shows zone.js usage counts drop to zero (or only intentional leftovers remain)
- No `fakeAsync` / `NgZone` / `zone.js` imports remain in source files (only in intentionally excluded files)

Generate a final report to `analysis_report/` using the template in `analysis_report/README.md`. Include:
- Components migrated
- Specs updated
- Remaining `fakeAsync`/`NgZone` usages (if any left)
- `ChangeDetectorRef.detectChanges()` usages not yet converted

---

## References

- `references/zoneless-api.md` — Full API reference (signals, providers, CDR)
- `references/spec-migration.md` — Detailed spec migration with examples
- `references/common-issues.md` — Known issues, gotchas, and fixes
