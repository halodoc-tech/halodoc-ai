# Research Checklist

The input is only a name, so the playbook is only as good as this research step.
Goal: assemble a grounded picture before you write anything. Ground every claim
in a retrieved source; mark anything unconfirmed.

## What every playbook needs (all input types)

- Plain-language description (what it is, what it does)
- Severity / exploitation status (is it being used in the wild? PoC public? KEV?)
- Affected or targeted assets (products, OSes, services, sectors)
- MITRE ATT&CK technique set
- Candidate IOCs (with source and a note on volatility)
- At least two independent sources agreeing on the core facts

## CVE

Extract:
- CVSS v3.1/v4.0 base score and vector
- Affected products **and exact version ranges** (precision matters — "Confluence"
  is useless; "Confluence Data Center 8.0.0–8.5.3" is actionable)
- Whether it's in the **CISA KEV catalog** (decisive triage signal)
- Exploitation status: PoC published? exploited in the wild? ransomware-linked?
- The exploitation chain — pre-auth vs post-auth, network position required
- ATT&CK techniques for *exploitation and what follows* (e.g. Exploit Public-
  Facing Application T1190, then whatever post-exploitation is reported)

Query patterns:
- `CVE-XXXX-XXXXX` (lands NVD + vendor advisory)
- `CVE-XXXX-XXXXX CISA KEV`
- `CVE-XXXX-XXXXX exploited in the wild`
- `CVE-XXXX-XXXXX detection sigma`
- `CVE-XXXX-XXXXX <product> affected versions`

## Malware family

Extract:
- Type (ransomware, loader, RAT, infostealer, wiper, C2 framework…)
- Delivery / initial access (phishing, exploit, malvertising, supply chain)
- Persistence, privilege escalation, defense evasion behaviors
- C2 characteristics (protocols, known infrastructure patterns)
- Host and network artifacts (file paths, registry keys, mutexes, JA3, user-agents)
- ATT&CK techniques — many families have a dedicated ATT&CK Software page that
  lists these directly; start there.

Query patterns:
- `<malware> MITRE ATT&CK techniques`
- `<malware> TTPs analysis` (favor DFIR Report, Red Canary, Unit 42, Talos)
- `<malware> IOC indicators`
- `<malware> sigma detection rule`
- `<malware> behavior persistence C2`

## APT / threat actor

Extract:
- Aliases (groups carry many vendor-specific names — capture them; analysts search
  by whichever name they know)
- Attribution and typical targeting (sectors, regions)
- Known tooling and malware used
- ATT&CK techniques — ATT&CK Group pages list mapped techniques + associated
  software directly; this is the best starting point.
- Notable recent campaigns

Query patterns:
- `<group> MITRE ATT&CK group`
- `<group> aliases also known as`
- `<group> recent campaign <current year>`
- `<group> tools malware used`
- `<group> TTPs detection`

## Disambiguation note

Malware names and group names overlap heavily, and the same artifact may be a
tool used by several groups. If the input is ambiguous, research both readings and
state the disambiguation in the Threat Summary rather than silently picking one.

## Source quality

Prefer primary and vendor research over aggregator/SEO content. If sources
conflict (common with attribution and version ranges), present the conflict rather
than averaging it away — the analyst needs to know the fact is contested.
