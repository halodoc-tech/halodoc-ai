# Analysis Report Directory

Generated migration analysis reports are saved here by the `analyze-zone-usage.sh` script.

## Generate a Report

Run from project root:

```bash
bash <skill-path>/scripts/analyze-zone-usage.sh [src-dir]
```

> Find `<skill-path>`: `find ~/.claude -path "*/angular-zoneless/scripts" -type d 2>/dev/null | head -1`

Output: `analysis_report/zone-usage-YYYYMMDD-HHMMSS.md`

## Report Contents

Each report includes:

- Zone.js polyfill import locations
- Files using `NgZone`
- `NgZone.run()` / `runOutsideAngular()` call sites
- `ApplicationRef.tick()` call sites
- `fakeAsync` / `tick()` usage in spec files
- Components missing `ChangeDetectionStrategy.OnPush`
- `ChangeDetectorRef.detectChanges()` call sites
- Summary table with counts

## Usage Workflow

1. Run `analyze-zone-usage.sh` → get baseline report
2. Work through migration phases (see SKILL.md)
3. Re-run script → verify counts drop to zero
4. Keep final report as migration completion evidence
