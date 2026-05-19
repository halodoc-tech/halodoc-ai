#!/usr/bin/env bash
# Find change detection patterns that need updating for zoneless migration.
# Run from project root: bash <skill-path>/scripts/find-cd-patterns.sh [src-dir]

set -euo pipefail

SRC="${1:-src}"

echo "=== Change Detection Migration Scan ==="
echo "Directory: $SRC"
echo ""

section() {
  echo "--- $1 ---"
}

section "Components missing ChangeDetectionStrategy.OnPush"
while IFS= read -r file; do
  if ! grep -q "ChangeDetectionStrategy.OnPush" "$file" 2>/dev/null; then
    echo "  MISSING: $file"
  fi
done < <(grep -rl "@Component" "$SRC" --include="*.ts" 2>/dev/null | grep -v "\.spec\.ts")
echo ""

section "detectChanges() calls in source files (not specs)"
grep -rn "\.detectChanges()" "$SRC" --include="*.ts" | grep -v "\.spec\.ts:" 2>/dev/null || echo "  (none)"
echo ""

section "markForCheck() calls (review if signals cover these)"
grep -rn "\.markForCheck()" "$SRC" --include="*.ts" | grep -v "\.spec\.ts:" 2>/dev/null || echo "  (none)"
echo ""

section "NgZone injections and usage"
grep -rn "NgZone\|ngZone" "$SRC" --include="*.ts" | grep -v "\.spec\.ts:" 2>/dev/null || echo "  (none)"
echo ""

section "ApplicationRef.tick() usage"
grep -rn "\.tick()" "$SRC" --include="*.ts" | grep -v "\.spec\.ts:" 2>/dev/null || echo "  (none)"
echo ""

section "setTimeout / setInterval without signal update (review these)"
grep -rn "setTimeout\|setInterval" "$SRC" --include="*.ts" | grep -v "\.spec\.ts:" | grep -v "//.*setTimeout" 2>/dev/null || echo "  (none)"
echo ""

section "fakeAsync in spec files"
grep -rn "fakeAsync\|tick(" "$SRC" --include="*.spec.ts" 2>/dev/null || echo "  (none)"
echo ""

section "flushMicrotasks in spec files"
grep -rn "flushMicrotasks" "$SRC" --include="*.spec.ts" 2>/dev/null || echo "  (none)"
echo ""

section "zone.js/testing imports in spec setup"
grep -rn "zone.js/testing" "$SRC" 2>/dev/null || echo "  (none)"
echo ""

echo "=== Scan complete ==="
