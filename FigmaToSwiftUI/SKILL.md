---
name: figma-to-swiftui
description: Convert a Figma design into SwiftUI View + ViewModel files following your project's design system conventions, design tokens, and localisation rules. Use when asked to implement or generate a screen from a Figma URL.
---

# Figma → SwiftUI

Arguments: $ARGUMENTS

> Before executing this skill, read `references/DS_AGENTS.md`.
> It is the authoritative source for component catalogue, token conventions,
> and file naming. Architecture rules live in your project's `CLAUDE.md` — this
> skill covers only the Figma-specific execution steps on top of both.
>
> **Adapting for your project:** Replace `references/DS_AGENTS.md` with your
> own design system documentation, and update path references below to match
> your project's `CLAUDE.md` conventions.

---

## Arguments

When invoked, check for these arguments. If any required one is missing, ask for all missing ones in a single message — then proceed.

| Argument | Required | Example |
|---|---|---|
| `figma_url` | ✅ | `https://figma.com/design/ABC/MyApp?node-id=14-24` |
| `target_path` | ✅ | `Modules/Feature/Sources/MyFeature/` |
| `screen_name` | optional | `MyOnboardingScreen` — inferred from Figma layer if omitted |

**If arguments are missing, ask exactly this:**

```
To generate the screen I need a couple of details:

1. Figma URL — full link including node-id
2. Target path — module + feature folder (e.g. Modules/Feature/Sources/MyFeature/)
3. Screen name — optional, I'll infer from Figma if you skip this
```

---

## Figma MCP

Use the remote endpoint. If it fails, stop and report — do not proceed.

| | Endpoint |
|---|---|
| Remote | `https://mcp.figma.com/mcp` |

Always scope calls to the specific node ID. Never fetch a root frame or full page.

---

## Execution Protocol

> **SwiftLint constraint (enforced throughout):** Every file generated must pass
> `swiftlint lint --path <target_path>` with zero violations. Apply this as a
> generation constraint — check output against SwiftLint rules before presenting it.
> Do not defer linting to a separate verification step.

### Step 1 — Fetch design context

Call `get_design_context(nodeId:, fileKey:)`. If the node is too large, drill into sublayer node IDs until you have full detail.

Extract:
- Layout direction (vertical / horizontal / wrap / overlap)
- All component instance names and node IDs
- Spacing, padding, inset values
- Color hex values and their semantic role
- Typography (family, size, weight, line-height)
- Interactive states

**Also detect and record these flags — they gate later steps:**

| Flag | Detection rule |
|---|---|
| `contains_images` | Any node has a fill of type `IMAGE` |
| `contains_animations` | Any layer name contains `lottie`, `animation`, `anim`, `gif`, or `loader`; or any prototype interaction uses `DISSOLVE` or `SMART_ANIMATE` on the node itself |

### Step 2 — Fetch component definitions

Call `get_code_connect_map(nodeId:, fileKey:)` to identify Code Connect mappings.

Map every component in this priority order — **refer to `references/DS_AGENTS.md` for the full component list**:
1. Code Connect mapped → use exactly as mapped
2. DS Organism → use it
3. DS Molecule → use it
4. DS Atom → use it
5. No DS equivalent → **stop and ask** (see Step 3)

### Step 2b — DS variant gap check

For every Code Connect–mapped or DS component, compare the Figma variant properties (e.g. `variant`, `size`, `state`, `type`, `style`) from `get_design_context` against the public API documented in `references/DS_AGENTS.md`.

If a Figma property has **no matching case or parameter** in the SDK component, stop and list all gaps in a single message before proceeding:

```
⚠️ DS variant gaps detected — resolve before code is written:

1. <ComponentName>: Figma uses `style: "ghost"` — no `ghost` case found in the SDK API.
   Options: A) Compose from primitives  B) Add TODO placeholder

2. <ComponentName>: Figma uses `<property>: "<value>"` — not found in SDK API.
   Options: A) Compose from primitives  B) Add TODO placeholder
```

Do not write any code until the developer responds to each gap.

### Step 3 — Handle missing DS equivalents

If any Figma component has no DS match at any tier:

1. Stop and name the unmapped component clearly.
2. Ask the developer to choose:
   - **A)** Compose from DS primitives + tokens (document the gap inline)
   - **B)** Add a `// TODO:` placeholder and skip for now
   - **C)** Add it to `references/DS_AGENTS.md` as a new known custom component
3. Do not write any code until the developer responds.

### Step 3b — Handle images *(skip entirely if `contains_images` is false)*

Before prompting, search for existing assets under `target_path` and any sibling `Assets.xcassets` directories:

```bash
find <target_path> -name "*.xcassets" -type d
```

List any asset names that match Figma layer names or descriptions. Then **stop and list all images in a single message**:

```
This screen contains X image(s). For each one, tell me how it should be loaded:

1. <Figma layer name / description>
   A) Asset name  — Image("asset_name", bundle: .module).resizable()
   B) Remote URL  — async image loading with a placeholder fallback
   C) Reuse "<found_asset_name>" already in the codebase  ← only shown if found

2. <Figma layer name / description>
   A/B/C ...
```

Wait for the developer's answer for **all images at once**. Then collect follow-ups in a single message:
- **If A**: "What is the asset name for image N?"
- **If B**: "What is the URL for image N?"
- **If C**: no follow-up needed — use the found asset name.

**Option A / C — Asset image**

```swift
Image("<asset_name>", bundle: .module)
    .resizable()
```

**Option B — Remote URL image**

Use your project's async image loading component (document it in `references/DS_AGENTS.md`).
Declare the URL as a property on the View and provide an asset placeholder:

```swift
struct <ScreenName>View: View {
    private let imageURL = "<url_from_developer>"

    var body: some View {
        loadImage(imageURL)
    }

    @ViewBuilder
    private func loadImage(_ imageUrl: String) -> some View {
        // Use your project's async image loading pattern here
    }
}
```

- Frame dimensions come from Figma — use tokens or explicit values only when Figma marks them fixed.
- The placeholder must be an asset image (Option A/C), never an SF Symbol unless the design explicitly shows one.

---

### Step 3c — Handle animations / GIFs *(skip entirely if `contains_animations` is false)*

Stop and ask:

```
This screen contains an animation. What is the Lottie JSON file name?
```

```swift
import Lottie

LottieView(animation: .named("<json_name>", bundle: .module))
    .looping()
```

- Always call `.looping()` unless the design clearly shows a one-shot animation.
- Apply `.frame(width:height:)` from Figma if the animation has a fixed size.

---

### Step 4 — Output component mapping and wait for confirmation

Do not write any Swift code until the developer confirms the table.

| # | Figma Layer | Code Connect? | DS Component | Key Props |
|---|---|---|---|---|
| 1 | `PrimaryButton` | Yes | `<YourButtonComponent>` | `style: .primary, size: .large` |
| 2 | `InputField` | No | `<YourInputComponent>` | `state: .normal` |

### Step 5 — Translate AutoLayout → SwiftUI

| Figma AutoLayout | SwiftUI |
|---|---|
| Vertical | `VStack(spacing: <YourTokenNamespace>.<spacingToken>)` |
| Horizontal | `HStack(spacing: <YourTokenNamespace>.<spacingToken>)` |
| Wrap | `LazyVGrid(columns: [...])` |
| Overlap | `ZStack` |
| Fill / flexible | `Spacer()` |
| Fixed size | `.frame(width:)` / `.frame(height:)` — only when Figma explicitly marks fixed |
| Padding | `.padding(<YourTokenNamespace>.<paddingToken>)` |

Replace `<YourTokenNamespace>` with your project's token type — see `references/DS_AGENTS.md`.

### Step 6 — Generate code

Only after Step 4 confirmation.

Produce two files per screen — follow naming and structure from `references/DS_AGENTS.md`:

- `<ScreenName>View.swift` — layout only, zero business logic
- `<ScreenName>ViewModel.swift` — all state, actions, dependencies

Token rules are in `references/DS_AGENTS.md` (Design Token Conventions). All rules there apply here.

### Step 6b — Add localisation keys

For every user-facing string in the generated view:

1. Look up the target module in the **Localisation table in your project's root `CLAUDE.md`**.
2. If the module is listed, add the key + primary-language value and secondary-language value to their respective `Localizable.strings` files at the documented paths.
3. If the module is **not listed**, stop and ask the developer for the correct localisation path before writing any keys.
4. Use `.localized` (or your project's equivalent extension) in code — never hardcode raw strings in the view:

```swift
Text("feature_title_label".localized)
```

Key naming: `snake_case`, descriptive of the UI element (e.g. `onboarding_start_button`, `empty_state_message`).

---

## File Placement

Write generated files under `target_path` following the folder structure defined
in your project's `CLAUDE.md`.
