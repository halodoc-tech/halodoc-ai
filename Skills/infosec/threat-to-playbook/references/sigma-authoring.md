# Sigma Authoring

Sigma rules in the playbook must be valid and CI-ready — they're meant to drop
straight into the rules repo and compile through GitLab CI into the log platform.
A rule that doesn't parse, or that targets telemetry you don't have, just creates
noise. Author deliberately.

## Required schema

Every rule includes these fields, in this order:

```yaml
title: <concise, specific — names the behavior, not the threat marketing name>
id: <a UUID v4 — generate a fresh one per rule>
status: experimental
description: <what this detects and why it indicates the threat>
references:
    - <URL the detection logic is grounded in>
author: SOC / Threat Intel
date: <YYYY-MM-DD>
tags:
    - attack.<tactic>            # e.g. attack.initial-access
    - attack.t<technique-id>     # e.g. attack.t1190
logsource:
    product: <e.g. aws | linux | windows | kubernetes>
    service: <e.g. cloudtrail | guardduty>   # when applicable
    category: <e.g. process_creation | proxy>  # when applicable
detection:
    selection:
        <field>: <value or list>
    condition: selection
falsepositives:
    - <realistic benign cause, or "Unknown">
level: <informational | low | medium | high | critical>
```

Rules:
- **`id` must be a real UUID v4**, unique per rule. Don't reuse or fabricate a
  pattern — generate one (e.g. `python3 -c "import uuid;print(uuid.uuid4())"`).
- **`tags` must carry the ATT&CK tactic and technique** so the rule self-maps in
  the pipeline. Use lowercase `attack.tNNNN` (and sub-techniques as
  `attack.tNNNN.NNN`). Only tag techniques you actually verified — these tags are
  the link back to the ATT&CK mapping section.
- **`references` must be real URLs** from the research step. If a rule is adapted
  from a SigmaHQ community rule, link it and keep its `id` lineage in a comment.
- **`level`** should reflect detection confidence, not threat severity — a noisy
  heuristic is `low` even for a critical CVE.

## logsource mapping

Point `logsource` at telemetry that actually exists (see
`soc-environment.md`). Common mappings:

| Detection target | logsource |
| --- | --- |
| AWS API/control-plane | `product: aws`, `service: cloudtrail` |
| AWS threat findings | `product: aws`, `service: guardduty` |
| Endpoint process exec | `product: <os>`, `category: process_creation` |
| Kubernetes control plane | `product: kubernetes`, `service: audit` |
| Web/API exploitation | `category: proxy` or `category: webserver` (Tyk-fed) |

If the right telemetry isn't collected, still write the prose detection, but
instead of a Sigma rule add a one-line note: `# DETECTION GAP: requires <source>,
not currently collected` — so it becomes a visible backlog item.

## Field-name realism

Sigma field names depend on the log schema the backend normalizes to. You won't
always know the exact field. When unsure, use the conventional Sigma field name
for that logsource (CloudTrail: `eventName`, `eventSource`, `userIdentity.type`;
process_creation: `Image`, `CommandLine`, `ParentImage`) and add a comment that
the field may need mapping to the local schema. Honest and adjustable beats
confidently wrong.

## Quality bar before including a rule

- Does it parse as valid YAML?
- Does the `condition` reference selections that exist?
- Is the technique tag verified, not guessed?
- Would it fire on the threat behavior AND have a defensible false-positive note?
- Is the `logsource` something the environment actually has?

If a rule can't clear this bar, ship the prose detection and the gap note instead
of a weak rule.

## GitLab CI / file conventions

- One rule per `.yml` file under `sigma/` in the output.
- Filename: `<technique-id>_<short-behavior>.yml`, e.g.
  `t1190_confluence_rce_exploit_attempt.yml`. Lowercase, underscores.
- Keep rules self-contained — no shared includes — so CI compiles each
  independently.
