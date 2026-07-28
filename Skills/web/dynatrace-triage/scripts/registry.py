#!/usr/bin/env python3
"""Attribution registry for auto-heal (Mode 3).

Persists the full fix lifecycle: error.id -> status -> branch -> MR -> verified
resolution, plus per-run metrics against the 75% remediation target.

usage:
  registry.py init    <registry.json> --run-id ID --csv PATH --base-sha SHA --repo PATH [--min-users 100]
  registry.py update  <registry.json> --run-id ID --error-id EID --status S
                      [--error-text T] [--users N] [--branch B] [--branch-point-sha SHA]
                      [--mr-url U] [--confidence-source S] [--confidence-fix F]
                      [--duplicate-group G] [--note "..."]
  registry.py preflight <registry.json> --run-id ID --result "already-enabled|enabled-in-mr <url>|failed: ..."
  registry.py finalize <registry.json> --run-id ID
  registry.py report  <registry.json> --run-id ID
  registry.py verify  <registry.json> --run-id ID --fresh-source PATH  (CSV or the canonical JSON row list; --fresh-csv also accepted)

Statuses:
  auto-fixed | auto-fixed-mr-pending | reported | skipped-3rd-party |
  skipped-below-threshold | resolved-verified | regressed-or-unmerged
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TARGET_RATE = 0.75
FIXED_STATUSES = {"auto-fixed", "auto-fixed-mr-pending"}
ELIGIBLE_STATUSES = FIXED_STATUSES | {"reported"}
SKIP_STATUSES = {"skipped-3rd-party", "skipped-below-threshold"}
ALL_STATUSES = ELIGIBLE_STATUSES | SKIP_STATUSES | {
    "resolved-verified", "regressed-or-unmerged",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"runs": [], "errors": {}}


def save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_run(data, run_id):
    for run in data["runs"]:
        if run["run_id"] == run_id:
            return run
    print(f"run not found: {run_id}", file=sys.stderr)
    raise SystemExit(1)


def compute_metrics(data, run_id):
    entries = [e for e in data["errors"].values() if run_id in e.get("runs", [])]
    auto_fixed = [e for e in entries if e["status"] in FIXED_STATUSES]
    reported = [e for e in entries if e["status"] == "reported"]
    skipped_3p = [e for e in entries if e["status"] == "skipped-3rd-party"]
    skipped_bt = [e for e in entries if e["status"] == "skipped-below-threshold"]
    eligible = len(auto_fixed) + len(reported)
    rate = (len(auto_fixed) / eligible) if eligible else None
    with_mr = [e for e in auto_fixed if e.get("mr_url")]
    return {
        "total_rows": len(entries),
        "eligible": eligible,
        "auto_fixed": len(auto_fixed),
        "reported": len(reported),
        "skipped_3rd_party": len(skipped_3p),
        "skipped_below_threshold": len(skipped_bt),
        "remediation_rate": round(rate, 4) if rate is not None else None,
        "target": TARGET_RATE,
        "target_met": (rate >= TARGET_RATE) if rate is not None else None,
        "mr_coverage": (round(len(with_mr) / len(auto_fixed), 4) if auto_fixed else None),
    }


def cmd_init(args):
    data = load(args.registry)
    if any(r["run_id"] == args.run_id for r in data["runs"]):
        print(f"run already exists: {args.run_id}", file=sys.stderr)
        return 1
    data["runs"].append({
        "run_id": args.run_id,
        "started_at": now(),
        "finished_at": None,
        "csv_path": args.csv,
        "repo": args.repo,
        "base_sha": args.base_sha,
        "min_users": args.min_users,
        "preflight": {"sourcemaps": None},
        "metrics": None,
    })
    save(args.registry, data)
    print(f"run initialized: {args.run_id}")
    return 0


def cmd_update(args):
    if args.status not in ALL_STATUSES:
        print(f"invalid status: {args.status} (valid: {sorted(ALL_STATUSES)})", file=sys.stderr)
        return 1
    data = load(args.registry)
    find_run(data, args.run_id)  # validates run exists
    entry = data["errors"].setdefault(args.error_id, {
        "status": None, "error_text": None, "users": None,
        "branch": None, "branch_point_sha": None, "mr_url": None,
        "source_confidence": None, "fix_confidence": None,
        "duplicate_group": None, "triage_writeup": None,
        "runs": [], "updated_at": None, "verified_at": None,
    })
    entry["status"] = args.status
    for field, value in [
        ("error_text", args.error_text), ("users", args.users),
        ("branch", args.branch), ("branch_point_sha", args.branch_point_sha),
        ("mr_url", args.mr_url),
        ("source_confidence", args.confidence_source),
        ("fix_confidence", args.confidence_fix),
        ("duplicate_group", args.duplicate_group),
        ("triage_writeup", args.note),
    ]:
        if value is not None:
            entry[field] = value
    if args.run_id not in entry["runs"]:
        entry["runs"].append(args.run_id)
    entry["updated_at"] = now()
    save(args.registry, data)
    print(f"{args.error_id}: {args.status}")
    return 0


def cmd_preflight(args):
    data = load(args.registry)
    run = find_run(data, args.run_id)
    run["preflight"]["sourcemaps"] = args.result
    save(args.registry, data)
    print(f"preflight recorded: {args.result}")
    return 0


def cmd_finalize(args):
    data = load(args.registry)
    run = find_run(data, args.run_id)
    run["metrics"] = compute_metrics(data, args.run_id)
    run["finished_at"] = now()
    save(args.registry, data)
    print(json.dumps(run["metrics"], indent=2))
    return 0


def fmt_pct(value):
    return "N/A" if value is None else f"{value * 100:.0f}%"


def cmd_report(args):
    data = load(args.registry)
    run = find_run(data, args.run_id)
    metrics = run.get("metrics") or compute_metrics(data, args.run_id)
    entries = {
        eid: e for eid, e in data["errors"].items()
        if args.run_id in e.get("runs", [])
    }

    lines = []
    lines.append(f"# Auto-Heal Run Report — {run['run_id']}")
    lines.append("")
    lines.append(f"- **Repo:** {run['repo']}")
    lines.append(f"- **CSV:** {run['csv_path']}")
    lines.append(f"- **Base SHA:** {run['base_sha']}")
    lines.append(f"- **Started:** {run['started_at']}  **Finished:** {run.get('finished_at') or 'in progress'}")
    lines.append(f"- **Sourcemap preflight:** {run['preflight'].get('sourcemaps') or 'not run'}")
    lines.append("")

    pending = [e for e in entries.values() if e["status"] == "auto-fixed-mr-pending"]
    if pending:
        lines.append("## ⚠️ Blockers")
        lines.append("")
        lines.append(f"- `glab` unavailable: {len(pending)} fixed branch(es) pushed without MR — run the recorded `glab mr create` commands.")
        lines.append("")

    rate = metrics["remediation_rate"]
    verdict = "TARGET MET ✅" if metrics["target_met"] else ("TARGET MISSED ❌" if metrics["target_met"] is not None else "N/A (no eligible errors)")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total rows | {metrics['total_rows']} |")
    lines.append(f"| Eligible | {metrics['eligible']} |")
    lines.append(f"| Auto-fixed | {metrics['auto_fixed']} |")
    lines.append(f"| Reported (low confidence) | {metrics['reported']} |")
    lines.append(f"| Skipped 3rd-party | {metrics['skipped_3rd_party']} |")
    lines.append(f"| Skipped below threshold | {metrics['skipped_below_threshold']} |")
    lines.append(f"| **Remediation rate** | **{metrics['auto_fixed']}/{metrics['eligible']} = {fmt_pct(rate)} — {verdict}** |")
    lines.append(f"| MR coverage of auto-fixed | {fmt_pct(metrics['mr_coverage'])} |")
    lines.append("")

    def table(title, statuses, columns):
        rows = [(eid, e) for eid, e in sorted(entries.items()) if e["status"] in statuses]
        if not rows:
            return
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| " + " | ".join(h for h, _ in columns) + " |")
        lines.append("|" + "---|" * len(columns))
        for eid, e in rows:
            lines.append("| " + " | ".join(str(fn(eid, e)) for _, fn in columns) + " |")
        lines.append("")

    table("Auto-Fixed", FIXED_STATUSES | {"resolved-verified", "regressed-or-unmerged"}, [
        ("Error ID", lambda eid, e: eid),
        ("Status", lambda eid, e: e["status"]),
        ("Users", lambda eid, e: e.get("users") or "?"),
        ("Confidence (src/fix)", lambda eid, e: f"{e.get('source_confidence') or '?'}/{e.get('fix_confidence') or '?'}"),
        ("Branch", lambda eid, e: f"`{e.get('branch') or ''}`"),
        ("MR", lambda eid, e: e.get("mr_url") or "pending"),
    ])
    table("Reported Only (low confidence)", {"reported"}, [
        ("Error ID", lambda eid, e: eid),
        ("Users", lambda eid, e: e.get("users") or "?"),
        ("Error", lambda eid, e: (e.get("error_text") or "")[:80]),
        ("Triage notes", lambda eid, e: (e.get("triage_writeup") or "")[:160]),
    ])
    table("Skipped", SKIP_STATUSES, [
        ("Error ID", lambda eid, e: eid),
        ("Reason", lambda eid, e: e["status"]),
        ("Users", lambda eid, e: e.get("users") or "?"),
        ("Notes", lambda eid, e: (e.get("triage_writeup") or "")[:120]),
    ])

    groups = {}
    for eid, e in entries.items():
        if e.get("duplicate_group"):
            groups.setdefault(e["duplicate_group"], []).append(eid)
    if groups:
        lines.append("## Duplicate Groups")
        lines.append("")
        for gid, ids in sorted(groups.items()):
            lines.append(f"- `{gid}`: {', '.join(sorted(ids))}")
        lines.append("")

    report = "\n".join(lines)
    out = Path(args.registry).parent / f"report-{run['run_id']}.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n[report saved: {out}]", file=sys.stderr)
    return 0


def load_fresh_ids(path):
    """Read the fresh pull's error ids — CSV (error.id column) or the
    canonical JSON row list (error_id key), detected by file extension."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("rows", data) if isinstance(data, dict) else data
        return {str(r.get("error_id") or "").strip() for r in rows if r.get("error_id")}
    with p.open(newline="", encoding="utf-8-sig") as handle:
        return {
            (row.get("error.id") or "").strip()
            for row in csv.DictReader(handle)
            if (row.get("error.id") or "").strip()
        }


def cmd_verify(args):
    data = load(args.registry)
    find_run(data, args.run_id)
    fresh_ids = load_fresh_ids(args.fresh_source)
    transitions = []
    for eid, entry in data["errors"].items():
        if entry["status"] not in FIXED_STATUSES:
            continue
        if eid in fresh_ids:
            entry["status"] = "regressed-or-unmerged"
            transitions.append((eid, "regressed-or-unmerged"))
        else:
            entry["status"] = "resolved-verified"
            entry["verified_at"] = now()
            transitions.append((eid, "resolved-verified"))
        if args.run_id not in entry["runs"]:
            entry["runs"].append(args.run_id)
        entry["updated_at"] = now()
    save(args.registry, data)
    for eid, status in transitions:
        print(f"{eid}: {status}")
    if not transitions:
        print("no auto-fixed entries to verify")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("registry", nargs="?", default=None,
                    help="registry.json path (falls back to $REGISTRY_PATH/registry.json)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--base-sha", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--min-users", type=int, default=100)
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("update")
    p.add_argument("registry", nargs="?", default=None,
                    help="registry.json path (falls back to $REGISTRY_PATH/registry.json)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--error-id", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--error-text")
    p.add_argument("--users", type=int)
    p.add_argument("--branch")
    p.add_argument("--branch-point-sha")
    p.add_argument("--mr-url")
    p.add_argument("--confidence-source")
    p.add_argument("--confidence-fix")
    p.add_argument("--duplicate-group")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("preflight")
    p.add_argument("registry", nargs="?", default=None,
                    help="registry.json path (falls back to $REGISTRY_PATH/registry.json)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser("finalize")
    p.add_argument("registry", nargs="?", default=None,
                    help="registry.json path (falls back to $REGISTRY_PATH/registry.json)")
    p.add_argument("--run-id", required=True)
    p.set_defaults(fn=cmd_finalize)

    p = sub.add_parser("report")
    p.add_argument("registry", nargs="?", default=None,
                    help="registry.json path (falls back to $REGISTRY_PATH/registry.json)")
    p.add_argument("--run-id", required=True)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("verify")
    p.add_argument("registry", nargs="?", default=None,
                    help="registry.json path (falls back to $REGISTRY_PATH/registry.json)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--fresh-source", "--fresh-csv", dest="fresh_source", required=True,
                    help="CSV export or canonical JSON row list from the latest pull")
    p.set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    if not args.registry:
        env_dir = os.environ.get("REGISTRY_PATH")
        if not env_dir:
            print(
                "registry path required: pass it as the first argument, or set "
                "$REGISTRY_PATH (e.g. REGISTRY_PATH=/persisted/ci/workspace) — "
                "the home-relative default is not safe in CI, where $HOME may be "
                "ephemeral or different per job",
                file=sys.stderr,
            )
            return 2
        args.registry = str(Path(env_dir) / "registry.json")
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
