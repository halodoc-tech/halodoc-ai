#!/usr/bin/env bash
# Analyze Zone.js usage in an Angular project.
# Run from the project root: bash <skill-path>/scripts/analyze-zone-usage.sh

set -euo pipefail

SRC="${1:-src}"
REPORT_DIR="analysis_report"
REPORT_FILE="$REPORT_DIR/zone-usage-$(date +%Y%m%d-%H%M%S).md"

mkdir -p "$REPORT_DIR"

echo "Scanning: $SRC"
echo ""

{
  echo "# Zone.js Usage Analysis Report"
  echo "Generated: $(date)"
  echo "Scanned: $SRC"
  echo ""

  echo "## Zone.js polyfill imports"
  echo '```'
  grep -rn "import 'zone.js'" "$SRC" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## NgZone injections"
  echo '```'
  grep -rn "NgZone" "$SRC" --include="*.ts" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## NgZone.run() calls"
  echo '```'
  grep -rn "\.run\s*(" "$SRC" --include="*.ts" | grep -v "//.*\.run\s*(" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## runOutsideAngular() calls"
  echo '```'
  grep -rn "runOutsideAngular" "$SRC" --include="*.ts" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## ApplicationRef.tick() calls"
  echo '```'
  grep -rn "\.tick()" "$SRC" --include="*.ts" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## fakeAsync usage in specs"
  echo '```'
  grep -rn "fakeAsync\|tick(" "$SRC" --include="*.spec.ts" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## Components without OnPush strategy"
  echo '```'
  while IFS= read -r file; do
    if ! grep -q "ChangeDetectionStrategy.OnPush" "$file" 2>/dev/null; then
      echo "$file"
    fi
  done < <(grep -rl "@Component" "$SRC" --include="*.ts" 2>/dev/null | grep -v ".spec.ts")
  echo '```'
  echo ""

  echo "## ChangeDetectorRef.detectChanges() calls (non-test)"
  echo '```'
  grep -rn "detectChanges()" "$SRC" --include="*.ts" | grep -v ".spec.ts" 2>/dev/null || echo "(none found)"
  echo '```'
  echo ""

  echo "## Summary"
  ZONE_IMPORTS=$(grep -rl "import 'zone.js'" "$SRC" 2>/dev/null | wc -l | tr -d ' ')
  NGZONE_FILES=$(grep -rl "NgZone" "$SRC" --include="*.ts" 2>/dev/null | wc -l | tr -d ' ')
  FAKEASYNC_FILES=$(grep -rl "fakeAsync" "$SRC" --include="*.spec.ts" 2>/dev/null | wc -l | tr -d ' ')
  NO_ONPUSH=$(while IFS= read -r file; do
    if ! grep -q "ChangeDetectionStrategy.OnPush" "$file" 2>/dev/null; then echo "$file"; fi
  done < <(grep -rl "@Component" "$SRC" --include="*.ts" 2>/dev/null | grep -v ".spec.ts") | wc -l | tr -d ' ')

  echo "| Item | Count |"
  echo "|---|---|"
  echo "| Zone.js polyfill imports | $ZONE_IMPORTS |"
  echo "| Files using NgZone | $NGZONE_FILES |"
  echo "| Spec files using fakeAsync | $FAKEASYNC_FILES |"
  echo "| Components missing OnPush | $NO_ONPUSH |"

} | tee "$REPORT_FILE"

echo ""
echo "Report saved to: $REPORT_FILE"
