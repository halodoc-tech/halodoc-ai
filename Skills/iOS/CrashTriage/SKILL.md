---
name: ios-crash-triage
description: Triages iOS crashes end to end — parses Firebase Crashlytics reports, Xcode .ips logs, or raw stack traces; classifies the crash (force unwrap, array bounds, dangling pointer, race condition, stack overflow, assertion, main-thread violation, OOM); locates the root cause in the project's own source; proposes a Swift fix following the team's documented conventions; and produces a ticket draft for the team's issue tracker. Use when a developer pastes or uploads an iOS crash artifact, names an iOS crash signal (EXC_BAD_ACCESS, EXC_BAD_INSTRUCTION, SIGABRT, SIGSEGV, "unexpectedly found nil", OOM), or asks "why is the iOS app crashing", "triage this crash", "fix this crash", "analyse this Crashlytics issue". Does not cover Android, React Native, or Flutter crashes, backend errors, or non-crash defects such as UI glitches, hangs, or slow performance.
---

# iOS Crash Triage

Full pipeline: **parse input → classify crash → root cause → fix → ticket draft**

**Completion bar:** a triage is not done at "here's what the exception means."
It is done when Steps 1–5 have all produced output, including a concrete fix and a ticket draft.

> Before triaging, always read `references/team-conventions.md`.
> It contains your team's module owners, known recurring crashes,
> custom ticket fields, and coding conventions. This is what makes fixes
> actionable rather than generic.
>
> **Adapting for your project:** Replace the placeholders in
> `references/team-conventions.md` with your own team's information
> (see Setup in `README.md`). The workflow below is project-agnostic —
> only the reference file needs customizing.
>
> **If `references/team-conventions.md` is missing:** proceed, but prefix the output with
> `⚠️ No team conventions found — using Swift defaults. Fill in references/team-conventions.md for project-specific fixes.`
>
> **If a section still contains `[Add …]` placeholders:** that section is unconfigured.
> Do not invent a value. For unconfigured logging, use the project's existing logging call
> (grep the crashing file for `os_log`, `Logger`, `print`, or a custom logger) and fall back to
> `// TODO: replace with your project's logger` if none is found. Apply the same rule to
> navigation, error-state, and analytics calls — mirror what the surrounding code already does.

---

## Step 1 — Identify Input Format

| What the dev provided | Action |
|---|---|
| Firebase Crashlytics report (JSON / pasted text) | Parse per § Firebase Parsing |
| Firebase issue ID / Crashlytics URL, Firebase MCP server connected | Fetch directly — see § Direct Crashlytics Access |
| Xcode crash log / `.ips` file | Parse per § Xcode Parsing |
| Raw stack trace pasted in chat | Extract frames directly |
| Crash type only, no trace | Ask the 4 questions in § Symptom Only |

**Multiple crashes in one input?** Triage each one fully and separately (repeat Steps 1–4 per
crash) rather than merging them into a single analysis — different crashes rarely share a root
cause even if they look similar.

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
Ask the team to upload dSYMs (requires the Firebase CLI: npm install -g firebase-tools):
  firebase crashlytics:symbols:upload --app=<APP_ID> <PATH_TO_DSYM>
Check whether the CI/CD pipeline uploads dSYMs in its post-archive step.
```

---

## § Direct Crashlytics Access

If a Firebase-related MCP server is connected, first check what it actually exposes — tool names
vary by implementation and are not standardized:
- Use `ToolSearch` (or your harness's tool-discovery mechanism) with a query like "crashlytics" or
  "crash issue" to find an issue-fetching tool.
- If a matching tool is found, use its fully-qualified `ServerName:tool_name` form to fetch the
  issue instead of asking for a paste.
- If no matching tool exists, or the call fails for any reason, fall back to asking the developer
  to paste the report — never block on it or retry a tool name that doesn't exist.

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
| `0x8badf00d` / watchdog / `SIGKILL` | → § Watchdog Termination (main thread blocked > 20s — find the sync I/O or blocking lock on main) |
| Crash inside a third-party framework, no app frames | → Report the framework, its version, and the call your app makes into it. Do not propose changes to vendor code. |

**No row matches?** Do not force-fit a class. Output `Crash Class: unclassified`, state the exception
type and subtype verbatim, list the top 5 frames, and give the developer the two most likely
hypotheses with what evidence would confirm each. An honest "unclassified" beats a wrong class.

---

## Step 2.5 — Ground the Fix in Real Source (mandatory)

Before proposing any fix, locate and read the actual code:

1. Take the first app frame from Step 1 (e.g. `ConsultationViewModel.loadDoctor`).
2. Find the file: `Glob` for `**/<TypeName>.swift`; if that misses, `Grep` for `func <methodName>`.
   If more than one file matches, prefer the one whose path matches the module named in the crash
   frame (e.g. a frame from `PaymentKit` → the `.swift` file under `Sources/PaymentKit/` or
   `Modules/Payment/`); if still ambiguous, list the candidates and ask.
3. Read the crashing function plus its callers (`Grep` for `<methodName>(`).
4. Confirm the crash class from Step 2 against what the code actually does.
5. Check the deployment target and Swift version in `references/team-conventions.md` (or the
   `.xcodeproj` / `Package.swift`). Do not propose API newer than the target supports —
   `guard let self else` needs Swift 5.7+, `actor` and `@MainActor` need Swift 5.5+.
6. **If the source contradicts the Step 2 classification** (e.g. the "crashing" line is a guarded
   optional, not a force unwrap), stop and re-classify: return to Step 2 with what the code actually
   shows, state that the signal-based classification was provisional, and note the corrected class
   before continuing to Step 3.

**If the file cannot be found** (source not in the workspace, or unsymbolicated frames),
say so explicitly and label the output:
`⚠️ Pattern-based analysis — source not available. Fix is illustrative, not verified against your code.`
Never emit a `File:` / `Line:` value you have not read.

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
guard indexPath.row < items.count else {
    Logger.log("Index \(indexPath.row) out of bounds (count: \(items.count)) in \(#function)", level: .error)
    return UITableViewCell()
}
let item = items[indexPath.row]
```

The guard prevents the crash; it does not fix the cause. Always also find why the count diverged —
mutation off the main thread, or a reload racing pagination.

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
// ✅ Preferred (Swift 5.5+) — actor isolation, checked by the compiler
actor ItemStore {
    private var items: [Item] = []
    func append(_ item: Item) { items.append(item) }
    func all() -> [Item] { items }
}

// ✅ Legacy fallback — only if the file is not yet async/await-capable
private let queue = DispatchQueue(label: "com.yourcompany.app.<feature>.queue")
private var _items: [Item] = []
func append(_ item: Item) { queue.async { self._items.append(item) } }
func getItems() -> [Item] { queue.sync { _items } }
```

Match the surrounding file. If it already uses async/await, use the actor form; if it's
completion-handler based, use the GCD form rather than mixing paradigms in one file.

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
// ✅ Preferred — compiler-enforced main-thread isolation
@MainActor
func refresh() async {
    let data = await viewModel.fetchData()
    tableView.reloadData()
}

// ✅ Legacy fallback for completion-handler APIs
viewModel.fetchData { [weak self] data in
    DispatchQueue.main.async { self?.tableView.reloadData() }
}
```

Match the surrounding file. If it already uses async/await, use the `@MainActor` form; if it's
completion-handler based, use the GCD form rather than mixing paradigms in one file.

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

**This skill proposes; it does not apply.** Output the fix as a diff in chat. Do not edit source
files, create branches, or file tickets unless the developer explicitly asks ("apply the fix",
"make the change"). After presenting the output, offer: "Want me to apply this fix?"

Always output all five sections in this order (Root Cause, Crash Class, Suggested Fix, How to
Verify, Ticket Draft — the redaction step below runs between the last two). When a section cannot
be completed from available evidence, emit the header and state what is blocking it — e.g.
`**File:** unknown — frames unsymbolicated, dSYM upload required`. Never fill a section with a guess
to avoid leaving it empty.

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

**1. Compile first.** Before reporting the fix as ready:
- `xcodebuild -scheme <Scheme> -destination 'generic/platform=iOS Simulator' build` (or `tuist build`)
- `swiftlint lint --path <ChangedFile>.swift` if a `.swiftlint.yml` exists
If either fails, fix and re-run before presenting. Never present unverified code as a fix.

**2. Then reproduce.** [How to reproduce locally or confirm the fix. E.g.: "Run the doctor booking flow with a nil appointmentId and verify no crash occurs. Enable Zombie Objects in Scheme diagnostics."]

### 🔒 Before the Ticket Draft — Redact

**Redact before writing the ticket draft.** Crash artifacts often carry personal data. Replace, in every
quoted log line, URL, and custom key/value:

| Found | Replace with |
|---|---|
| Email addresses, phone numbers | `<redacted-pii>` |
| User IDs, session IDs, auth tokens, deeplink query values | `<redacted-id>` |
| Device UUID / IDFV / IDFA | `<redacted-device-id>` |
| Patient, order, or transaction identifiers | `<redacted-record-id>` |

Keep exception type, signal, frames, file names, line numbers, OS and device *model* — these carry
no personal data and are what the fix depends on.

### 🎫 Ticket Draft

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

## Out of Scope

This skill does NOT:
- Triage Android, React Native, or Flutter crashes — those need their own platform skill
- Symbolicate crash logs (request a dSYM upload instead) or upload dSYMs
- File tickets — it produces the ticket draft only
- Handle non-crash defects: UI glitches, hangs without a crash, slow performance, layout bugs
- Configure Crashlytics alerting thresholds or monitoring

If the input is not an iOS crash, say so and stop rather than adapting the workflow.

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

---

## Worked Example

See `references/worked-example.md` for a full input → Step 4 output run.
