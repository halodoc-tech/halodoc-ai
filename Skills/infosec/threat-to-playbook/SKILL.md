---
name: threat-intel-to-soc-playbook
description: >-
  Convert a threat intelligence reference — a CVE ID, malware family, or
  APT/threat-actor name — into a ready-to-use, MITRE ATT&CK-mapped SOC playbook
  containing Sigma detection rules (GitLab-CI ready) and analyst response steps.
  Use this whenever someone supplies a threat identifier and wants detection and
  response built around it: e.g. "build a SOC playbook for CVE-2024-3094",
  "detection + IR steps for LockBit", "we need a runbook for APT29", "the new
  Confluence RCE just dropped, what should the SOC do", or "map this malware to
  ATT&CK and write Sigma for it". Trigger even when the word "playbook" is absent
  but the user clearly wants SOC detection/response guidance organized around a
  named threat.
---

# Threat Intel → SOC Playbook

This skill turns a *named threat* into an operational SOC playbook. The analyst
gives you only an identifier — a CVE, a malware family, or a threat group — and
you do the research, map it to MITRE ATT&CK, and produce detection logic (Sigma +
prose) and a response runbook tailored to the defender's environment.

The value is speed under pressure: when a new threat surfaces, the on-call SOC
shouldn't have to read ten vendor blogs and hand-author Sigma from scratch. This
skill compresses that into a single grounded artifact they can act on and push
straight into the detection pipeline.

## Why grounding matters more than usual here

A SOC playbook is an *operational* document. Wrong detection logic is worse than
none — it creates false confidence and noisy alerts. So the cardinal rule is:
**never invent ATT&CK technique IDs, CVE details, affected versions, or IOCs.**
Every technique mapping, indicator, and version claim must trace to a retrieved
source. When something can't be confirmed, say so explicitly ("no public ATT&CK
mapping found for this technique as of <date>") rather than guessing. A defender
can work with a known gap; they can't work with a confident fabrication.

## Workflow

### 1. Classify the input

Determine which of three forms you were given, because each drives different
research:

- **CVE** (e.g. `CVE-2024-3094`) → vulnerability-centric. Focus on affected
  products/versions, exploitation status, and the exploitation chain.
- **Malware family** (e.g. `LockBit`, `Cobalt Strike`) → behavior-centric. Focus
  on TTPs, delivery, persistence, C2, and host/network artifacts.
- **APT / threat actor** (e.g. `APT29`, `Lazarus`) → campaign-centric. Focus on
  the group's known techniques, tooling, and targeting.

If the input is ambiguous (could be a malware name or a group alias — these
overlap constantly), research both readings and note the disambiguation in the
Threat Summary.

### 2. Research and enrich (web_search)

Pull from authoritative sources, in rough priority order:

1. **MITRE ATT&CK** (attack.mitre.org) — the technique groundtruth. For
   groups/software, ATT&CK pages list mapped techniques directly.
2. **NVD / NIST** (nvd.nist.gov) — for CVEs: CVSS, affected configs, references.
3. **CISA** — advisories and the Known Exploited Vulnerabilities (KEV) catalog.
   KEV membership is the single most important triage signal for a CVE.
4. **Reputable vendor threat intel** — CrowdStrike, Mandiant/Google TIG,
   Microsoft, Cisco Talos, Unit 42, Red Canary, The DFIR Report. The DFIR Report
   and Red Canary are especially good for concrete detection/Sigma ideas.
5. **Sigma community ruleset** (github.com/SigmaHQ/sigma) — check whether
   published rules already exist; adapt rather than reinvent, and credit them.

Run several searches — don't stop at one. You're assembling: a plain-language
description, exploitation/severity status, affected assets, the ATT&CK technique
set, and candidate IOCs. See `references/research-checklist.md` for the per-input
extraction checklist and good query patterns.

### 3. Assess relevance to the environment

A generic playbook is half a playbook. Before writing detection, map the threat
to the defender's actual stack — what's exposed, where the telemetry lives, and
what response levers exist. Read `references/soc-environment.md` for the
telemetry sources and response tooling to reference. If the user's environment
clearly differs from what's documented there, ask or adapt; don't force-fit.

### 4. Map to MITRE ATT&CK

Build a tactic → technique table covering how *this specific threat* operates.
Include the technique ID, name, the governing tactic, and a one-line procedure
("how this threat uses it"). Prefer techniques you can actually detect with
available telemetry — a beautiful mapping you have no logs for is documentation,
not detection. Flag the coverage gaps explicitly so they become backlog items.

### 5. Write detection (Sigma + prose) per technique

For each detectable technique, produce both:

- **Prose detection guidance** — which telemetry source, what the analyst is
  looking for, and the logic in words. This survives even when the Sigma can't be
  perfectly tuned to the environment.
- **A Sigma rule** — valid, CI-ready YAML, ATT&CK-tagged, with the logsource
  pointed at the right telemetry. One rule per technique where it makes sense.
  Follow `references/sigma-authoring.md` exactly — it covers the schema, tagging,
  logsource mapping, false-positive handling, and the GitLab CI file conventions.

Save Sigma rules as separate `.yml` files under a `sigma/` directory in the output
so they drop straight into the rules repo, and reference each from the playbook.

### 6. Write triage and response

Cover triage (initial checks + how to set Jira severity), investigation queries
per data source, and then containment → eradication → recovery, each referencing
concrete tooling (e.g. host isolation via the EDR, scoping via the cloud security
findings). Keep it actionable: an analyst at 2am should be able to follow it.

### 7. Assemble and deliver

Assemble the playbook using `references/playbook-template.md` as the exact
structure. Output as a markdown file plus the `sigma/` rule files. Then present
the files. Lead with a 2-3 sentence summary of severity, exposure, and the
single most important first action — that's what the analyst reads first.

## Output structure

Follow `references/playbook-template.md` precisely so every playbook is
predictable to navigate. The top-level sections are: Threat Summary →
Environment Relevance → ATT&CK Mapping → Detection (per technique) → Triage &
Investigation → Response → IOCs → References & Coverage Gaps.

## Reference files

- `references/research-checklist.md` — per-input-type extraction checklist and
  search query patterns. Read at step 2.
- `references/soc-environment.md` — telemetry sources and response tooling
  to ground detection/response in. Read at step 3.
- `references/sigma-authoring.md` — Sigma schema, ATT&CK tagging, logsource
  mapping, and CI conventions. Read at step 5.
- `references/playbook-template.md` — the exact output template. Read at step 7
  (or earlier to keep the end shape in mind).
