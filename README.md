# halodoc-ai

> **Open-source Claude Code skills from Halodoc Engineering.**

This repository is Halodoc's public home for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills — reusable AI workflows built by our engineering teams and shared freely with the developer community.

We believe AI-assisted engineering works best when the community builds together. These skills are the same quality bar we hold ourselves to internally, now available for anyone to use, fork, and improve.

---

## What are Claude Code skills?

Skills are prompt bundles that give Claude Code domain-specific expertise for your engineering workflows. Install a skill and Claude automatically activates it when your intent matches — no commands to memorize, no configuration required.

Think of them as reusable engineering playbooks that Claude can execute: writing TCDs from PRDs, generating code from designs, triaging crashes, scanning for security issues, and more — all triggered through natural language.

Learn more about Claude Code skills → [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code)

---

## Skills

> Skills are being added progressively. Star or watch this repo to be notified as new ones land.

Skills are organized by engineering domain:

```
skills/
├── backend/        # API design, code generation, deployment workflows
├── frontend/       # Component generation, design-to-code, performance
├── android/        # Android SDLC, crash analysis, migration tooling
├── ios/            # iOS SDLC, SwiftUI generation, memory and crash tooling
├── sre/            # Deployment safety, incident analysis, outage prevention
├── data/           # Pipeline onboarding, schema management, datalake tooling
└── security/       # OWASP scanning, compliance checks, vulnerability triage
```

Each skill folder contains a `SKILL.md` (what Claude reads) and a `README.md` (what you read). See any skill's `README.md` for its specific inputs, triggers, and requirements.

---

## Installation

### Install the full plugin

```bash
claude mcp add https://github.com/halodoc-tech/halodoc-ai
```

All skills in this repo become available in every Claude Code session.

### Install a single skill

Clone the repo and copy the skill you want into your project's `.claude/skills/` directory:

```bash
git clone https://github.com/halodoc-tech/halodoc-ai.git
cp -r halodoc-ai/skills/<domain>/<skill-name> your-project/.claude/skills/
```

### Reference from your `CLAUDE.md`

Point Claude Code at the cloned repo without copying files:

```markdown
## Skills
- path: ~/halodoc-ai/skills/backend
- path: ~/halodoc-ai/skills/android
```

---

## Usage

Skills are designed to feel natural. Just describe what you want in plain English:

```
"Write a TCD for the new notifications feature, PRD is at <url>"

"Analyse this crash from Firebase Crashlytics and find the root cause"

"Convert this Figma screen to a SwiftUI view: <figma-url>"

"Run an OWASP scan on this MR before I merge: <mr-url>"

"Generate a deployment checklist for these two MRs"
```

Claude reads your intent and loads the appropriate skill automatically.

---

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed
- An active Anthropic API key or Claude for Teams / Enterprise plan
- Individual skills may require additional credentials (e.g. a Figma access token, GitLab PAT). These are listed in each skill's `README.md`

---

## Contributing

We welcome contributions — new skills, prompt improvements, bug fixes, and documentation updates.

### Adding a new skill

1. Fork this repository
2. Create your skill under `skills/<domain>/<your-skill-name>/`
3. Include both `SKILL.md` and `README.md` (use [`docs/skill-template/`](docs/skill-template/) as a starting point)
4. Add at least one eval fixture under `evals/<domain>/`
5. Open a pull request using the `New Skill` PR template

### Improving an existing skill

- For prompt improvements or bug fixes, open a PR with a clear before/after description of the behavior change
- For breaking changes (different inputs, different outputs), bump the version in the `SKILL.md` header and document the change in `CHANGELOG.md`

### Reporting issues

Open a [GitHub Issue](https://github.com/halodoc-tech/halodoc-ai/issues) with as much context as possible: what you asked Claude, what skill triggered, and what you expected vs. what happened.

For security vulnerabilities, please email **security@halodoc.com** instead of filing a public issue.

---

## Repository structure

```
halodoc-ai/
├── README.md
├── CHANGELOG.md
├── skills/
│   ├── backend/
│   ├── frontend/
│   ├── android/
│   ├── ios/
│   ├── sre/
│   ├── data/
│   └── security/
├── docs/
│   ├── getting-started.md
│   ├── authoring-guide.md
│   └── skill-template/
│       ├── SKILL.md
│       └── README.md
└── evals/
```

---

## About Halodoc

[Halodoc](https://www.halodoc.com) is the number one all-around healthcare application in Indonesia. Our mission is to simplify and deliver quality healthcare across Indonesia, from Sabang to Merauke.

Since 2016, Halodoc has been improving health literacy in Indonesia by providing user-friendly healthcare communication, education, and information (KIE). Our ecosystem offers a full range of services for convenient healthcare access:

- **Homecare by Halodoc** — preventive care that lets users conduct health tests privately and securely from home
- **My Insurance** — seamless access to cashless outpatient benefits
- **Chat with Doctor** — consultations with over 20,000 licensed physicians via chat, video, or voice call
- **Health Store** — medicines, supplements, and health products from a network of over 4,900 trusted partner pharmacies
- **Digital Clinic (Haloskin)** — a trusted dermatology care platform guided by experienced dermatologists

We are proud to be trusted by global and regional investors including the Bill & Melinda Gates Foundation, Singtel, UOB Ventures, Allianz, GoJek, Astra, Temasek, and many more. With over USD 100 million raised to date, our team remains steadfast in our journey to simplify healthcare for all Indonesians.

Our engineering teams have been embedding AI into their daily workflows to keep pace with that mission. This repository is part of that journey made public — tools we built for ourselves that we think can help others too.

Engineering blog → [engineering.halodoc.com](https://engineering.halodoc.com)  
LinkedIn → [linkedin.com/company/halodoc](https://www.linkedin.com/company/halodoc)

---