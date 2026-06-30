# Playbook Template

Use this exact structure so every playbook is predictable to navigate at 2am.
Fill placeholders; delete sections only when truly N/A (and say why).

```markdown
# SOC Playbook: <Threat Name / ID>

> **Analyst TL;DR:** <2–3 sentences: what it is, severity + exploitation status,
> and the single most important first action.>

## 1. Threat Summary

| Field | Value |
| --- | --- |
| Identifier | <CVE / malware / group> |
| Type | <Vulnerability / Malware / Threat actor> |
| Aliases | <other names> |
| First seen / Disclosed | <date> |
| Severity | <CVSS or qualitative> |
| Exploitation status | <KEV? PoC? in-the-wild? ransomware-linked?> |
| Affected / Targeted | <products + versions, or sectors> |

<One paragraph plain-language description.>

## 2. Environment Relevance

<Which parts of our stack are exposed or in scope. Concrete exposure-assessment
steps the analyst can run now — e.g. "check Security Hub for <product>", "query
CloudTrail for <API>". If exposure is unknown, say what to check to find out.>

**Recommended Jira severity:** <Critical/High/Medium/Low + one-line justification>

## 3. MITRE ATT&CK Mapping

| Tactic | Technique ID | Technique | Procedure (how this threat uses it) |
| --- | --- | --- | --- |
| <tactic> | T<id> | <name> | <one line> |

## 4. Detection

### T<id> — <Technique Name> (<Tactic>)

- **Telemetry:** <source(s) from the environment>
- **Logic:** <prose detection guidance>
- **Sigma:** `sigma/<filename>.yml`  *(or:* `DETECTION GAP: requires <source>` *)*

<Repeat per detectable technique.>

## 5. Triage & Investigation

1. <initial triage check>
2. <investigation query per data source>
...
<Include how to set the Jira ticket: severity, key fields, what to attach.>

## 6. Response

**Containment**
- <action + tool>

**Eradication**
- <action + tool>

**Recovery**
- <action + tool>

## 7. Indicators of Compromise

| Type | Indicator | Confidence | Source | Notes |
| --- | --- | --- | --- | --- |
| <ip/domain/hash/...> | <value> | <high/med/low> | <ref> | <volatility note> |

> IOCs are the most perishable part of this playbook — treat host/network
> behavior (sections 4–6) as the durable detection, IOCs as a fast first sweep.

## 8. References & Coverage Gaps

**Sources**
- <URL> — <what it provided>

**Detection coverage gaps**
- <technique with no telemetry / no rule yet — becomes backlog>
```

## Notes on filling it in

- The TL;DR is the most-read line. Make it decisive.
- Keep section 2 specific to the environment — that's what separates this from a
  generic vendor write-up.
- Section 8's coverage-gaps list is a feature, not an admission. It turns the
  playbook into a detection-engineering backlog.
