# iOS — Team Crash Conventions (template)
# ─────────────────────────────────────────────────────────────
# This file is your team's living knowledge base for crash triage.
# The skill (SKILL.md) reads this file on every triage run.
#
# HOW TO CONTRIBUTE:
#   - Add a new known crash pattern under § Known Recurring Crashes
#   - Add module ownership under § Module Owners
#   - Add a new team convention under § Coding Conventions
#   - Add a custom ticket field under § Issue Tracker Config
#   - Keep entries concise — one paragraph per pattern max
#   - Add your name + date when adding a pattern so others know who to ask
# ─────────────────────────────────────────────────────────────

> ⚠️ **This file will contain internal information — owner names, chat handles, wiki links,
> dashboard URLs.** Keep it in your own private repo. Never commit a filled-in copy back to a
> public repository or upstream fork. If you contribute improvements to this skill, submit the
> placeholder template only.

## Contents
- [§ Coding Conventions](#-coding-conventions) — architecture, naming, logging, SwiftLint
- [§ Module Owners](#-module-owners) — who to assign each crash to
- [§ Issue Tracker Config](#-issue-tracker-config) — tracker, project key, priority definitions
- [§ Known Recurring Crashes](#-known-recurring-crashes) — patterns seen more than once
- [§ Team Debugging Checklist](#-team-debugging-checklist) — run before escalating
- [§ Do Not Rules](#-do-not-rules) — fixes that have caused problems before
- [§ References](#-references) — architecture guide, SwiftLint config, dashboards

---

## § Coding Conventions

**Naming prefix:** [Add your team's class prefix convention, if any, e.g. `HD` for Halodoc, `ACME` for AcmeCorp — leave blank if you don't use one]
Examples: `<Prefix>ConsultationViewModel`, `<Prefix>HomeCoordinator`, `<Prefix>UserSession`, `<Prefix>NetworkManager`

**Architecture:** [Add your architecture pattern, e.g. MVVM + Coordinator, VIPER, TCA]
- [Add the responsibility boundaries for each layer, e.g. "ViewModels own business logic — never put network calls in ViewControllers"]
- [Add navigation ownership rules, e.g. "Coordinators own all navigation — never call `navigationController.push` from a VC directly"]
- [Add view-layer rules, e.g. "Views are passive — they only call ViewModel methods and bind to outputs"]

**Logging:** Use `[Add your logging utility, e.g. AppLogger]` for all diagnostic output. Never use `print` in production code.
```swift
Logger.log("Message here", level: .error)   // levels: debug, info, warning, error, fault
```

**SwiftLint rules enforced (crash-relevant):**
- No force unwrap `!` — use `guard let` or `if let`
- No force cast `as!` — use `guard let x = y as? T`
- Trailing closure syntax preferred
- Max function length: [Add your limit, e.g. 40 lines]
- No implicit return in multi-line closures

**Minimum iOS target:** [Add your deployment target, e.g. iOS 14.0]
**Swift version:** [Add your Swift version, e.g. Swift 5.9+]

---

## § Module Owners
# When suggesting a fix or creating a ticket draft, assign to the module owner.
# Format: Module — Owner — Slack/Teams handle

| Module | Owner | Contact |
|---|---|---|
| [Add module, e.g. Consultation / Booking] | [Add owner] | [Add handle] |
| [Add module, e.g. Home / Dashboard] | [Add owner] | [Add handle] |
| [Add module, e.g. Authentication / Session] | [Add owner] | [Add handle] |
| [Add module, e.g. Payment / Checkout] | [Add owner] | [Add handle] |
| [Add module, e.g. Network Layer] | [Add owner] | [Add handle] |
| [Add module, e.g. Design System Components] | [Add owner] | [Add handle] |

---

## § Issue Tracker Config

**Tool:** [Add your issue tracker, e.g. JIRA, Linear, GitHub Issues]
**Project key:** [Add your project key, e.g. IOS]
**Bug issue type:** Bug
**Crash-specific labels:** `crash`, `ios-crash`, `needs-triage`

**Priority definitions:**
- **P0** — [Add your team's P0 criteria, e.g. "Crash on app launch, login, or payment. Blocks all users. Requires same-day fix."]
- **P1** — [Add your team's P1 criteria, e.g. "Crash on a core flow. High user impact."]
- **P2** — [Add your team's P2 criteria, e.g. "Crash on secondary screen or rare edge case. Low frequency."]
- **P3** — [Add your team's P3 criteria, e.g. "Crash only in specific edge case or on unsupported OS. Low urgency."]

**Custom fields to populate (if applicable):**
- `Affects Version` — get from the Firebase release version
- `Device` — from Firebase: top affected device model
- `OS Version` — from Firebase: top affected iOS version
- `Crash Rate` — affected users % from Firebase issue overview

---

## § Known Recurring Crashes
# Add patterns your team has seen more than once.
# Format: crash title, trigger condition, fix summary, added by, date

---

### [TEMPLATE — copy this block to add a new pattern]
**Crash:** [Short name, e.g. "ConsultationViewModel nil doctor on re-entry"]
**Trigger:** [When does it happen? E.g. "User navigates back and re-enters a screen quickly"]
**Root Cause:** [One sentence]
**Fix Applied:** [PR link or file + line description]
**Added by:** [Your name] — [Date]

---

### Example: HomeCoordinator deeplink crash
**Crash:** Force unwrap on deeplink parameter in `HomeCoordinator.handleDeeplink()`
**Trigger:** User opens a malformed or expired deeplink from a push notification
**Root Cause:** `url.queryParameters["itemId"]!` — assumes parameter always present
**Fix Applied:** Replace with `guard let itemId = url.queryParameters["itemId"] else { return }`
**Added by:** Jane Doe — 2025-01-01

---

## § Team Debugging Checklist
# Steps every dev should run before escalating a crash

1. **Symbolicate first** — confirm frames show file/line info, not hex addresses
2. **Check Firebase crash-free sessions %** — is this above your P1 threshold?
3. **Reproduce locally** — run the user flow on a device matching the top affected OS/device from Firebase
4. **Enable diagnostics in Xcode scheme:**
   - Address Sanitizer (for EXC_BAD_ACCESS)
   - Thread Sanitizer (for race conditions / SIGBUS)
   - Main Thread Checker (for UI-on-background-thread)
   - Zombie Objects (for dangling pointer / use-after-free)
5. **Check recent PRs** — did the crash start after a specific merge? Check git log for the affected file
6. **Search your team chat** — search the crash class name or ViewController — someone may have seen it before

---

## § Do Not Rules
# Patterns that have caused issues in the past — do not suggest these as fixes

- **Do not** use `DispatchQueue.main.sync` from the main thread — causes deadlock
- **Do not** use `unowned` in closures across async boundaries — use `weak` instead
- **Do not** call `reloadData()` from inside `cellForRowAt` — causes recursive layout
- **Do not** access `UIApplication.shared` from a background thread
- **Do not** use `UserDefaults` for storing sensitive data (auth tokens, user PII)

---

## § References
- Internal Architecture Guide: [Add Confluence/Notion link]
- SwiftLint config: `.swiftlint.yml` in repo root
- Firebase Crashlytics dashboard: [Add link]
- dSYM upload script: [Add path, e.g. `scripts/upload_dsyms.sh`]
