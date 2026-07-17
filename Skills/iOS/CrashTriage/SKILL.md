---
name: ios-crash-triage
description: Use this skill whenever a developer needs to analyze, diagnose, or fix an iOS crash. Triggers include: pasting a stack trace, sharing a Firebase Crashlytics report, uploading an Xcode .ips crash log, mentioning a crash type (EXC_BAD_ACCESS, nil unwrap, retain cycle, OOM), or asking "why is the app crashing". Also use when the developer says "triage this crash", "help me fix this crash", "what's causing this", or uploads any crash-related file. Produces full crash triage: root cause analysis + Swift fix following your project's conventions + issue-tracker ticket draft. Always use this skill proactively — don't just summarize the crash, go all the way to a fix.
---

# iOS Crash Triage

Full pipeline: **parse input → classify crash → root cause → fix → issue ticket**

> Before triaging, always read `references/team-conventions.md`.
> It contains your team's module owners, known recurring crashes,
> custom ticket fields, and coding conventions. This is what makes fixes
> actionable rather than generic.
>
> **Adapting for your project:** Replace the placeholders in
> `references/team-conventions.md` with your own team's information
> (see Setup in `README.md`). The workflow below is project-agnostic —
> only the reference file needs customizing.

---

## Step 1 — Identify Input Format

| What the dev provided | Action |
|---|---|
| Firebase Crashlytics report (JSON / pasted text) | Parse per § Firebase Parsing |
| Xcode crash log / `.ips` file | Parse per § Xcode Parsing |
| Raw stack trace pasted in chat | Extract frames directly |
| Crash type only, no trace | Ask the 4 questions in § Symptom Only |

---

## § Firebase Parsing

Look for these fields in order:

1. **Exception type** — line starting with `Fatal Exception:` or `Signal:`
2. **Exception reason** — the message on the next line (e.g. `nil value unexpectedly found`)
3. **Crashing thread** — section marked `Crashed:` or `com.apple.main-thread`
4. **First app frame** — first line containing your app's bundle identifier (e.g. `com.yourcompany.app`) — this is the entry point into app code
5. **Caller chain** — 2–3 frames above that first app frame

**Unsymbolicated frames** look like: `0x000000010012abc4`
If you see these, tell the developer:
```
Frames are unsymbolicated — file/line info is missing.
Ask the team to upload dSYMs:
  firebase crashlytics:symbols:upload --app=<APP_ID> <PATH_TO_DSYM>
Check if the CI/CD pipeline uploads dSYMs post-archive step.
```

---

## § Xcode / .ips Parsing

Key fields to extract:

```
Exception Type:     EXC_BAD_ACCESS (SIGSEGV)
Exception Subtype:  KERN_INVALID_ADDRESS at 0x0000000000000010
Triggered by Thread: 0

Thread 0 Crashed:
0   libswiftCore.dylib    0x... swift_retain
1   com.yourcompany.app   0x... ConsultationViewModel.loadDoctor (ConsultationViewModel.swift:142)
```

Extract: exception type + subtype, triggered thread, queue name, first frame matching your app's bundle identifier.

---

## § Symptom Only (no trace)

Ask these 4 questions before proceeding:
1. Is there a Firebase issue ID or issue title?
2. Which screen / user flow does it happen on?
3. Is it reproducible or random?
4. Did it start after a specific release or PR?

Then match to the closest crash class in Step 2.

---

## Step 2 — Classify the Crash

| Signal / Message | Crash Class |
|---|---|
| `unexpectedly found nil`, `EXC_BAD_INSTRUCTION` | → § Nil / Force Unwrap |
| `Index out of range` | → § Array Bounds |
| `EXC_BAD_ACCESS (SIGSEGV)` | → § Dangling Pointer or Race Condition |
| `EXC_BAD_ACCESS (SIGBUS)` | → § Race Condition |
| Deep recursive identical frames | → § Stack Overflow |
| `Fatal error: assertion failed`, `preconditionFailure` | → § Assertion |
| `UI API called on background thread` | → § Main Thread Violation |
| No stack trace, OOM label in Firebase | → § OOM |
| `SIGABRT` + Swift runtime message | → Check for assertion or KVO misuse |

---

## Step 3 — Fix Patterns by Crash Class

### § Nil / Force Unwrap

**Root cause:** A value assumed non-nil was nil at runtime. Usually API response fields, coordinator parameters, or auth state.

```swift
// ❌ Before
let doctorId = response.data!.doctorId!

// ✅ After
guard let data = response.data, let doctorId = data.doctorId else {
    Logger.log("Missing doctor data in response", level: .error)
    showErrorState()
    return
}
```

**Also check:** `as!` casts — replace with `guard let x = y as? Type`.

---

### § Array Bounds

**Root cause:** Array mutated on a background thread between `numberOfRows` and `cellForRow`, or paginated data count changed mid-render.

```swift
// ❌ Before
let item = items[indexPath.row]

// ✅ After
guard indexPath.row < items.count else { return UITableViewCell() }
let item = items[indexPath.row]
```

Also verify the array isn't mutated off main thread — wrap mutations in `DispatchQueue.main.async`.

---

### § Dangling Pointer / Missing weak self

**Root cause:** Closure captures `self` strongly; `self` is deallocated before the closure executes.

```swift
// ❌ Before
viewModel.onDataLoaded = { [self] data in
    self.updateUI(data)
}

// ✅ After
viewModel.onDataLoaded = { [weak self] data in
    guard let self else { return }
    self.updateUI(data)
}
```

**Note:** Don't add `weak self` blindly to synchronous closures — only needed when the closure outlives `self`.

---

### § Race Condition

**Root cause:** Shared mutable state read/written from multiple threads simultaneously.

```swift
// ✅ Fix — serial dispatch queue
private let queue = DispatchQueue(label: "com.yourcompany.app.<feature>.queue")
private var _items: [Item] = []

func append(_ item: Item) {
    queue.async { self._items.append(item) }
}
func getItems() -> [Item] {
    queue.sync { _items }
}
```

---

### § Stack Overflow

**Root cause:** Infinite recursion — common in Coordinator `start()` deeplink loops or `didSet` property cycles.

```swift
// ❌ Before — didSet triggers itself
var isLoading: Bool = false {
    didSet { isLoading = validate() }
}

// ✅ After
var isLoading: Bool = false {
    didSet {
        guard oldValue != isLoading else { return }
        validate()
    }
}
```

For Coordinator loops: trace the `start()` → `navigate()` chain and find where it re-enters `start()`.

---

### § Assertion / Precondition

**Root cause:** A developer guard was hit in production — the condition it protects was violated.

```swift
// ❌ Before — crashes in production
precondition(user.isLoggedIn, "User must be logged in")

// ✅ After — safe fallback
guard user.isLoggedIn else {
    Logger.log("Unexpected: not logged in at \(#function)", level: .fault)
    coordinator?.navigateToLogin()
    return
}
```

Read the assertion message literally — it tells you exactly what invariant was violated.

---

### § Main Thread Violation

**Root cause:** UIKit/SwiftUI API called from a background thread (network callback, Combine operator, etc).

```swift
// ✅ Fix
viewModel.fetchData { [weak self] data in
    DispatchQueue.main.async {
        self?.tableView.reloadData()
    }
}
```

Enable **Main Thread Checker** in Xcode → Edit Scheme → Diagnostics → Runtime API Checking.

---

### § OOM (Out of Memory)

**Root cause:** Memory exhaustion — usually undownsampled images, leaked view controllers, or accumulating closures.

```swift
// ✅ Downsample images before display
func downsample(imageAt url: URL, to size: CGSize) -> UIImage? {
    let options = [kCGImageSourceShouldCache: false] as CFDictionary
    guard let source = CGImageSourceCreateWithURL(url as CFURL, options) else { return nil }
    let thumbOptions = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceShouldCacheImmediately: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: max(size.width, size.height)
    ] as CFDictionary
    guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbOptions) else { return nil }
    return UIImage(cgImage: cgImage)
}
```

Use **Instruments → Leaks + Allocations** to find retained objects. Run Memory Graph Debugger in Xcode during the leaking flow.

---

## Step 4 — Produce Output

Always output in this structure. Never skip a section.

---

### 🔍 Root Cause
[One clear paragraph. Name the class, file, and line if known. Describe the exact condition that triggers the crash — not just "nil was found" but *why* it was nil.]

### ⚠️ Crash Class
`[class name from Step 2]`

### 🛠 Suggested Fix

**File:** `[FileName.swift]`
**Line:** `[line number or "unknown — search for <symbol>"]`

```swift
// Before / After as shown in Step 3 patterns
```

**Why this fixes it:** [1–2 sentences.]

### 🧪 How to Verify
[How to reproduce locally or confirm the fix. E.g.: "Run the doctor booking flow with a nil appointmentId and verify no crash occurs. Enable Zombie Objects in Scheme diagnostics."]

### 🎫 Issue Ticket

> Formatted for JIRA below — adjust field names for your team's tracker (Linear, GitHub Issues, etc.). See `references/team-conventions.md` for your project's priority definitions and custom fields.

**Title:** `[iOS] [ScreenName] — [Crash class]: [Short description]`
**Priority:** `[P0 / P1 / P2]` — see `references/team-conventions.md` for your team's priority definitions
**Component:** iOS
**Labels:** `crash`, `[module-name]`

```
## Summary
[One sentence.]

## Steps to Reproduce
1.
2.
3. Crash occurs

## Expected Behavior
[What should happen.]

## Actual Behavior
App crashes: [exception type + message]

## Root Cause
[From Root Cause section above.]

## Proposed Fix
[File + summary of fix.]

## Crash Rate
[From Firebase if available: affected users %, crash-free sessions %]
```

---

## Step 5 — Common Mistakes to Avoid

1. **Top frame ≠ bug location.** The actual bug is usually 2–3 frames below the crash site.
2. **Don't silence with empty catch/guard.** Always log or handle the failure path.
3. **Don't add `weak self` everywhere.** Synchronous closures don't need it.
4. **Partial threading fixes crash intermittently.** Verify the entire callback chain is on the correct thread.
5. **`as?` returning nil is not a fix** unless you handle the nil case.
6. **Don't resolve unsymbolicated crashes by guessing.** Request dSYM upload first.

---

## Quick Reference

| Exception | Most Likely Cause | First Thing to Check |
|---|---|---|
| `EXC_BAD_INSTRUCTION` + nil message | Force unwrap | Find `!` near crashing line |
| `EXC_BAD_ACCESS (SIGSEGV)` | Dangling pointer | Missing `weak self` in closure |
| `EXC_BAD_ACCESS (SIGBUS)` | Race condition | Shared mutable state + threads |
| `SIGABRT` + assertion | Precondition violated | Read the assertion message |
| `Index out of range` | Array bounds | Concurrent mutation or count mismatch |
| OOM / no trace | Memory exhaustion | Instruments Leaks + image sizes |
| Deep recursive frames | Stack overflow | Coordinator loops, `didSet` cycles |
| `UI API on background thread` | Main thread violation | Wrap in `DispatchQueue.main.async` |
