# SOC Environment

Ground detection and response in the actual stack so the playbook is operational,
not generic. The table below is an **example cloud-native SOC stack** — treat it
as a starting point and customize it to your own environment.

> **Customize this file.** Replace the telemetry sources and response tooling
> below with what your SOC actually runs. The rest of the skill is
> environment-agnostic and reads from here, so editing this one file re-targets
> every playbook to your stack. If a user's environment clearly differs from
> what's documented here, adapt or ask rather than force-fitting.

## Telemetry sources (where detections look)

| Source | What it sees | Use for detecting |
| --- | --- | --- |
| Central log platform (Sigma target) | Aggregated logs from the sources below; this is what compiled Sigma rules run against | Most detections — this is the primary detection surface |
| Cloud threat-detection service (e.g. AWS GuardDuty) | Account/network/DNS threat findings | Recon, C2 beaconing, crypto-mining, credential-abuse, exfil in the cloud |
| Cloud posture/findings hub (e.g. AWS Security Hub) | Aggregated security findings + posture | Misconfig exposure, prioritizing detection findings |
| Cloud control-plane audit (e.g. AWS CloudTrail) | API/control-plane activity | Privilege escalation, persistence, defense evasion (IAM changes, key creation, logging tampering) |
| Kubernetes audit logs | Cluster control-plane API calls | Container escape attempts, RBAC abuse, suspicious exec/pod creation |
| API gateway logs | API request/response traffic | Exploitation of public-facing apps/APIs (T1190), abuse, enumeration |
| EDR (e.g. CrowdStrike Falcon) | Endpoint process/file/network telemetry | Execution, persistence, priv-esc, lateral movement, C2 on hosts |

When mapping a technique to detection, pick the source that actually has the
signal. A Sigma rule with `logsource` pointing at telemetry you don't collect is a
documented gap, not a detection — call it out as such.

## Response tooling (what analysts can actually do)

| Capability | Tool category | Notes |
| --- | --- | --- |
| Host containment | EDR | Network-isolate a host while keeping EDR connectivity |
| Cloud scoping/containment | Cloud IAM + audit + network | Revoke keys, disable users, tighten security groups, snapshot for forensics |
| Exposure assessment | Posture hub + threat-detection service | Determine which assets match the threat's affected profile |
| API-layer mitigation | API gateway | Rate-limit, block, or patch routing for an exploited endpoint |
| Detection deployment | CI pipeline | Sigma rules compile via CI into the log platform (see sigma-authoring.md) |
| Case management | Ticketing (e.g. Jira) | Alerts auto-create tickets; playbook should specify severity + fields |

## Severity → ticket guidance

When the playbook tells the analyst to raise/triage a ticket, give a concrete
severity recommendation tied to the threat, e.g.:

- **Critical** — actively exploited (e.g. on the CISA KEV list) AND affected asset confirmed exposed
- **High** — affected asset present, exploitation feasible, no confirmed exposure
- **Medium** — relevant TTPs but no confirmed affected asset
- **Low / Track** — informational; build detection, no current exposure

Keep these as recommendations the analyst confirms, not automated verdicts.
