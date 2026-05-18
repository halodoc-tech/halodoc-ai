# DS_AGENTS.md — Design System Reference

> **This file is a portable reference bundled with the figma-to-swiftui skill.**
> Replace all placeholder content with your project's actual design system.
>
> The skill reads this file at the start of every run to:
> - Map Figma component names to Swift types (Steps 2, 4)
> - Detect variant/property gaps before code generation (Step 2b)
> - Apply the correct token namespace in generated code (Steps 5, 6)
> - Write localisation keys to the right paths (Step 6b)
>
> Keeping it current is critical — an outdated catalogue causes silent gaps.

---

## ✅ Component Catalogue

One row per DS component. The `Accepted Parameters` column must list every valid
enum case — this is what the variant gap check (Step 2b) compares against.

| Figma Name | Swift Type | Accepted Parameters |
|---|---|---|
| `PrimaryButton` | `<YourButtonComponent>` | `style: (.primary, .secondary)`, `size: (.small, .medium, .large)`, `title: String` |
| `TextInput` | `<YourInputComponent>` | `state: (.normal, .focused, .error, .disabled)`, `placeholder: String` |
| *(add all DS components)* | | |

For complex components with non-trivial init signatures, add a code block:

```swift
// Example — replace with your actual types
public struct <YourButtonComponent>: View {
    public enum Style { case primary, secondary /* add all cases */ }
    public enum Size  { case small, medium, large }
    public init(style: Style, size: Size, title: String, action: () -> Void) { ... }
}
```

---

## ✅ Design Token Conventions

| Token type | Swift namespace | Example usage |
|---|---|---|
| Color | `<YourTokenNamespace>Color` | `<YourTokenNamespace>Color.textPrimary` |
| Spacing | `<YourTokenNamespace>Spacing` | `<YourTokenNamespace>Spacing.md` |
| Padding | `<YourTokenNamespace>Padding` | `<YourTokenNamespace>Padding.screen` |
| Typography | `<YourTokenNamespace>Font` | `<YourTokenNamespace>Font.bodyMedium` |
| Radius | `<YourTokenNamespace>Radius` | `<YourTokenNamespace>Radius.card` |

Rule: never hardcode hex values, raw color constructors, or raw numeric sizes.

**Async image loading component** — document the pattern here so Step 3b uses the correct type:

```swift
// Example — replace with your actual async image component
<YourAsyncImageComponent>(url: url) {
    placeholderView
} content: { image in
    image.resizable()
}
```

---

## ✅ File Naming Convention

| File | Pattern | Example |
|---|---|---|
| View | `<YourPrefix><ScreenName>View.swift` | `OnboardingView.swift` |
| ViewModel | `<YourPrefix><ScreenName>ViewModel.swift` | `OnboardingViewModel.swift` |
| Data / Config model | `<YourPrefix><ComponentName>Data.swift` | `ButtonData.swift` |

---

## App-Flavor / Theming (optional)

If your project supports multiple app flavors or themes, document the branching
pattern here so the skill can apply it during generation.

---

## Localisation Paths

| Module | Localizable.strings path |
|---|---|
| `<ModuleName>` | `<path>/en.lproj/Localizable.strings` |
| *(add all modules)* | |

---

## Known DS–Figma Gaps

Components that exist in Figma but have no DS equivalent. Document the agreed
composition approach so the skill reuses it consistently.

| Figma Component | Figma Variant | Agreed approach |
|---|---|---|
| `<FigmaName>` | `style: ghost` | Composed from `<PrimitiveA>` + `<PrimitiveB>` |
