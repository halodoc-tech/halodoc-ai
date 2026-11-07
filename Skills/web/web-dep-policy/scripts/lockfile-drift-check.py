#!/usr/bin/env python3
"""Lockfile drift check: compares the resolved name@version set of the working
tree's pnpm-lock.yaml against a git ref (default HEAD).

Usage, from the repo root:
    python3 lockfile-drift-check.py [ref]

Why this exists: pnpm format conversions and installs can silently re-resolve
ranged dependencies. Onboarding reviews demand that the ONLY version changes in
a lockfile diff are the governed bumps the developer approved. This script makes
that property checkable in seconds. It handles both lockfile formats:
  v6 (pnpm 8):  "  /name@1.2.3(peers):"
  v9 (pnpm 9+): "  name@1.2.3(peers):"  /  "  'name@1.2.3(peers)':"

Interpretation of the output:
  - "0 names with version-set changes"  -> perfectly faithful (required for the
    pnpm 8 -> 9 conversion commit).
  - Pure REMOVALS (old -> [])           -> orphaned duplicates GC'd by pnpm 10's
    peer resolution; expected during pnpm 10 onboarding, harmless.
  - Version CHANGES/ADDITIONS           -> must be exactly the governed deps the
    developer approved; anything else needs investigation before pushing.
"""
import re
import subprocess
import sys

REF = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
PAT = re.compile(r"^  '?/?((?:@[\w.-]+/)?[\w.-]+)@(\d[^(':]*)", re.M)


def resolved(text: str) -> dict:
    out: dict = {}
    for m in PAT.finditer(text):
        out.setdefault(m.group(1), set()).add(m.group(2))
    return out


old_text = subprocess.run(
    ["git", "show", f"{REF}:pnpm-lock.yaml"], capture_output=True, text=True
).stdout
try:
    new_text = open("pnpm-lock.yaml").read()
except FileNotFoundError:
    sys.exit("pnpm-lock.yaml not found — run from the repo root.")

old, new = resolved(old_text), resolved(new_text)
changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
removals = [k for k in changed if k in old and not new.get(k)]
real_changes = [k for k in changed if new.get(k) and old.get(k) != new.get(k)]

print(f"compared against {REF}: {len(changed)} names with version-set changes")
if removals:
    print(f"\npure removals ({len(removals)}) — usually orphan GC, verify nothing imports them:")
    for k in sorted(removals):
        print(f"  {k}: {sorted(old[k])} -> (gone)")
if real_changes:
    print(f"\nversion changes/additions ({len(real_changes)}) — each must be an approved governed bump:")
    for k in sorted(real_changes):
        print(f"  {k}: {sorted(old.get(k, []))} -> {sorted(new.get(k, []))}")
if not changed:
    print("perfectly faithful — zero resolution drift.")
sys.exit(0 if not real_changes else 1)
