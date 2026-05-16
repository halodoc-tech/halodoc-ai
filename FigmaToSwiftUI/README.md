# figma-to-swiftui

A Claude Code skill that converts a Figma screen into SwiftUI View + ViewModel
files, mapped to your project's design system components and tokens. It handles
component resolution, variant gap detection, image and animation prompting,
localisation key generation, and SwiftLint compliance — all before writing a
single line of code.

---

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Figma MCP connected (`https://mcp.figma.com/mcp`)
- SwiftLint installed and configured for your project
- Your design system documented in `references/DS_AGENTS.md` (see Setup)

---

## Setup

**1. Copy the skill into your project**

Place this folder anywhere Claude Code can reach it and register it in your
`CLAUDE.md` or skills config:

```
your-project/
└── .claude/
    └── skills/
        └── figma-to-swiftui/
            ├── SKILL.md
            └── references/
                └── DS_AGENTS.md
```

**2. Populate `references/DS_AGENTS.md`**

This is the only file you must fill in. Open it and replace the placeholder
sections with your project's actual design system documentation:

| Section | What to put there |
|---|---|
| Component Catalogue | Every DS component, its Swift type name, its Figma component name, and its full public API (enum cases, init params) |
| Design Token Conventions | Your token namespace(s), types, and usage pattern |
| File Naming Convention | How your project names View and ViewModel files |
| Localisation Paths | Per-module paths to `Localizable.strings` |
| Known Gaps | Figma components that have no DS equivalent and the agreed composition approach |

The variant gap check (Step 2b) depends on the Component Catalogue being
accurate and up to date. If a component's accepted enum values are missing here,
gaps will go undetected.

**3. Cover architecture in your project's `CLAUDE.md`**

This skill deliberately does not own architecture rules. Make sure your
`CLAUDE.md` documents:

- MVVM conventions and responsibilities
- Folder structure under each module
- Any DI, navigation, or concurrency patterns

The skill reads `CLAUDE.md` for folder placement and localisation table — both
must be present there.

---

## Usage

Invoke the skill in Claude Code:

```
/figma-to-swiftui
```

Claude will ask for three things if not already provided:

| | |
|---|---|
| `figma_url` | Full Figma link including `node-id` |
| `target_path` | Module + feature folder to write files into |
| `screen_name` | Optional — inferred from Figma if omitted |

---

## What this skill does not cover

| Concern | Where it lives |
|---|---|
| MVVM architecture and folder conventions | Your project's `CLAUDE.md` |
| DS component implementation | Your design system source code |
| Navigation / routing | Your project's `CLAUDE.md` |
| DI / dependency wiring | Your project's `CLAUDE.md` |
| CI / build pipeline | Your project's CI config |

---

## Keeping it current

The skill is only as good as `references/DS_AGENTS.md`. Update it whenever:

- A new DS component is added or an existing one changes its public API
- A token namespace or naming convention changes
- A new module is added with a different localisation path
- A known Figma–DS gap is resolved or a new one is identified
