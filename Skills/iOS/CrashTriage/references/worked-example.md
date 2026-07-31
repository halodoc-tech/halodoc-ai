# Worked Example — Crashlytics report → complete triage output

**Input:**
```
Fatal Exception: EXC_BAD_INSTRUCTION
Unexpectedly found nil while unwrapping an Optional value
Crashed: com.apple.main-thread
0  MyApp  0x1024b8 BookingViewModel.confirm() (BookingViewModel.swift:87)
1  MyApp  0x1024a0 BookingViewController.didTapConfirm() (BookingViewController.swift:143)
```

**Output:**

### 🔍 Root Cause
`BookingViewModel.confirm()` force-unwraps `selectedSlot` at line 87. `selectedSlot` is only assigned
in `didSelectSlot(_:)`; when the confirm button is enabled by a cached form state on re-entry, it is
still nil. The crash is on the main thread at tap time, not during load.

### ⚠️ Crash Class
`nil / force unwrap`

### 🛠 Suggested Fix
**File:** `BookingViewModel.swift` · **Line:** `87`
```swift
// ❌ Before
let slot = selectedSlot!
// ✅ After
guard let slot = selectedSlot else {
    Logger.log("confirm() with no selected slot", level: .error)
    onValidationError?(.noSlotSelected)
    return
}
```
**Why this fixes it:** Converts an unrecoverable unwrap into a handled validation path, and surfaces
the real bug (confirm enabled before slot selection) instead of crashing.

### 🧪 How to Verify
Build, then open Booking → select a slot → back → re-enter → tap Confirm. Expect the validation
error, not a crash.

### 🎫 Ticket Draft
**Title:** `[iOS] [Booking] — Force unwrap: crash on Confirm after screen re-entry`
**Priority:** `P1` · **Labels:** `crash`, `booking`
*(body per the Step 4 template)*
