# Architecture Rules

## Quality Bar

A fix is only complete if it answers all of these:
- What was the runtime symptom?
- What exact runtime path triggered it?
- What is the actual root cause?
- Why is this fix better than a null guard or fallback-only patch?
- What regression risk exists?
- What test proves the failure path is covered?
- Could the same defect pattern exist in sibling components/modules?

## Fix Hierarchy

Prefer fixes in this order when evidence supports them:
1. restore the correct invariant or state contract
2. fix lifecycle ordering or async sequencing
3. fix the component/input/output contract
4. initialize state correctly
5. add SSR/browser guards where the environment is the real issue
6. add cleanup or teardown where lifecycle leakage is the issue
7. add defensive null guards or optional chaining only when the value is legitimately optional

Important rule:
- do not treat optional chaining or null guards as “root cause fixed” unless the missing value is valid by design
- if the value is supposed to exist, prefer fixing why it becomes missing

## Confidence Model

### Source Confidence

- `high`: 2 or more independent signals point to the same file/component
- `medium`: 1 strong signal points to a likely file, but mapping is incomplete
- `low`: only vague or indirect clues; vendor/minified stack dominates

### Fix Confidence

- `high`: root cause is coherent, minimal fix is clear, tests can cover it
- `medium`: patch is plausible but architectural cause is partly inferred
- `low`: patch would be speculative or merely suppressive

### Delivery Rule

- auto-apply, commit, push, and create MR/PR only when source confidence is not low and fix confidence is high or medium with clear assumptions
- if confidence is low, stop before commit and explicitly report why

### Auto-Heal Delivery Rule (Mode 3)

Same thresholds as above, but the consequence of low confidence changes:

- eligible + source confidence not low + fix confidence high, or medium with
  explicit assumptions → auto-fix, test-gate, MR — with NO human prompt
- medium fix confidence → the assumptions MUST be written into both the MR
  body and the registry entry
- low confidence (either axis) → registry status `reported` with a triage
  writeup, instead of stopping to ask the human
- never widen these thresholds to reach the remediation-rate target

## Common High-Quality Fix Patterns

- initialize state before dependent lifecycle code runs
- reorder logic so dependent code runs after data is ready
- tighten `@Input` handling in `ngOnChanges` with proper existence checks
- guard browser-only APIs with SSR-safe checks
- use `takeUntil(this.ngUnsubscribe$)` for teardown leaks
- validate array/object presence where data is truly optional

## Anti-Patterns

- optional chaining everywhere with no explanation
- declaring success before establishing source confidence
- fixing the symptom in the template when the contract is broken in the component or service

## Security Constraints

A fix must never introduce:
- `innerHTML` / `outerHTML` / `document.write` with unsanitized dynamic or
  user-controlled content
- Angular's `bypassSecurityTrust*` without an explicit, stated justification
- `eval()` / `new Function()` with dynamic input

If a fix genuinely requires rendering user-controlled content, use
framework-safe APIs (Angular template binding, `DomSanitizer`) — never raw
string interpolation into the DOM. This applies even when the root cause
diagnosis is otherwise correct; a security regression is worse than the
original bug.
