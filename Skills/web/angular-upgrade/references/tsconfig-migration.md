# tsconfig.json: `moduleResolution` for Modern Angular

> **Applies to every Angular version from 19 onwards** (19, 20, 21, 22, …). This is not a one-off v19 task — it is the baseline `tsconfig.json` requirement for any modern Angular target. If you are upgrading *to* any version ≥19, verify this regardless of which version you came from.

From Angular 19, the framework packages use the `exports` field in their `package.json` for all sub-path imports (e.g., `@angular/common/http`, `@angular/material/button`). TypeScript's legacy `"moduleResolution": "node"` does not read the `exports` field — it looks for physical subdirectories that no longer exist.

## Symptom

Mass `TS2307: Cannot find module` errors after upgrading Angular packages, especially for sub-path imports like `@angular/common/http`.

## Required Fix

Check these three settings in `tsconfig.json` **before** running the upgrade loop:

### Before (broken on Angular ≥19)

```json
{
  "compilerOptions": {
    "moduleResolution": "node",
    "module": "es2020",
    "paths": {
      "@angular/*": ["./node_modules/@angular/*"]
    }
  }
}
```

### After (correct)

```json
{
  "compilerOptions": {
    "moduleResolution": "bundler",
    "module": "preserve"
  }
}
```

### What to change

1. `"moduleResolution": "node"` → `"moduleResolution": "bundler"` — enables TypeScript to read `exports` maps
2. `"module": "es2020"` → `"module": "preserve"` — required with bundler mode
3. **Remove** any `"paths": { "@angular/*": [...] }` entry — it overrides the exports map and breaks all `@angular/*` sub-paths

Apply this fix **before Phase 3** (dependency upgrade), not after encountering errors.
