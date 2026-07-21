#!/usr/bin/env python3
"""Eligibility filter for auto-heal (Mode 3).

Reads error rows from ANY of the three acquisition paths — a Dynatrace Error
Inspector CSV export, or a canonical JSON row list produced by the live
browser-pull or token/DQL-pull workflows (see references/live-pull.md /
references/token-pull.md) — and emits a work-queue JSON:

- eligible errors (1st-party AND affected users >= threshold), sorted by
  affected users descending
- skipped errors with reasons (skipped-3rd-party / skipped-below-threshold)

1st-party is a HARD exclusion applied before the users threshold: any row
whose error text names a non-first-party domain (ad/analytics/CDN scripts,
browser extension schemes, opaque cross-origin "Script error.") is dropped
immediately — never merely flagged for later confirmation. The evidence-stage
stack-frame check in the auto-heal workflow is a second, stricter gate on top
of this.

usage:
  eligibility.py <csv_path> --first-party-domain example.com [--min-users 100] [--out queue.json]
  eligibility.py --json <rows.json> --first-party-domain example.com [--min-users 100] [--out queue.json]

--first-party-domain is REQUIRED — pass your own site's domain(s) (repeat the
flag for multiple). There is no default: guessing a domain for you would
silently misclassify every row on a project that isn't yours.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

# CSV-stage 3rd-party signals (cheap heuristics; authoritative confirmation
# happens later at the evidence/stack-frame stage — see references/eligibility.md).
VENDOR_PATTERNS = [
    r"\bgtag\b", r"\bgtm\b", r"googletagmanager", r"google_tag",
    r"\bfbq\b", r"facebook", r"\b_fbp\b",
    r"clevertap", r"moengage", r"\bappier\b",
    r"\bzE\b", r"zendesk",
    r"\bSentry\b", r"\bdtrum\b", r"\bnewrelic\b", r"\bNREUM\b",
    r"\bhotjar\b", r"\bmixpanel\b", r"\bamplitude\b",
    r"googlesyndication", r"doubleclick", r"adsbygoogle",
]
EXTENSION_SCHEMES = [
    "chrome-extension://", "moz-extension://", "safari-web-extension://",
    "safari-extension://", "ms-browser-extension://",
]
OPAQUE_CROSS_ORIGIN = re.compile(r"^\s*\"?Script error\.?\"?\s*$", re.IGNORECASE)
LEADING_HOSTNAME = re.compile(
    r"^\s*(?:https?://)?([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+)/"
)

VENDOR_RE = re.compile("|".join(VENDOR_PATTERNS), re.IGNORECASE)

# Column names as exported by Dynatrace Error Inspector.
COL_ID = "error.id"
COL_ERROR = "❌ Error"
COL_SEVERITY = "🚨 Severity"
COL_SIGNAL = "🧠 Signal"
COL_USERS = "👥 Users"
COL_COUNT = "🔁 Count"
COL_TEAMS = "👨‍💻 Teams"
COL_PAGES = "🌐 Top Pages"
COL_BROWSERS = "🌍 Browsers"

# Canonical JSON row keys (what live-pull.md / token-pull.md must emit).
JSON_KEYS = (
    "error_id", "error_text", "severity", "signal",
    "users", "count", "teams", "top_pages", "browsers",
)


def parse_int(value):
    """Parse ints like '4,120', ' 178 ', '"1 198"' (NBSP-safe). Unparseable -> (0, warning)."""
    if value is None:
        return 0, "missing value"
    if isinstance(value, int):
        return value, None
    cleaned = re.sub(r"[^\d]", "", str(value))
    if not cleaned:
        return 0, f"unparseable numeric value: {value!r}"
    return int(cleaned), None


def extract_domain(error_text):
    """Return the leading hostname if the error text looks like a script URL, else None."""
    m = LEADING_HOSTNAME.match(error_text or "")
    return m.group(1).lower() if m else None


def third_party_signals(error_text, first_party_domains):
    """Return list of hard-exclusion 3rd-party signals found in the error text."""
    signals = []
    text = error_text or ""
    if OPAQUE_CROSS_ORIGIN.match(text):
        signals.append("opaque-cross-origin: 'Script error.'")
    for scheme in EXTENSION_SCHEMES:
        if scheme in text:
            signals.append(f"extension-scheme: {scheme}")
    m = VENDOR_RE.search(text)
    if m:
        signals.append(f"vendor-pattern: {m.group(0)}")
    domain = extract_domain(text)
    if domain and not any(
        domain == fp or domain.endswith(f".{fp}") for fp in first_party_domains
    ):
        signals.append(f"non-first-party-domain: {domain}")
    return signals


def normalize_csv_row(row):
    return {
        "error_id": (row.get(COL_ID) or "").strip(),
        "error_text": (row.get(COL_ERROR) or "").strip(),
        "severity": (row.get(COL_SEVERITY) or "").strip(),
        "signal": (row.get(COL_SIGNAL) or "").strip(),
        "users": row.get(COL_USERS),
        "count": row.get(COL_COUNT),
        "teams": (row.get(COL_TEAMS) or "").strip(),
        "top_pages": (row.get(COL_PAGES) or "").strip(),
        "browsers": (row.get(COL_BROWSERS) or "").strip(),
    }


def normalize_json_row(row):
    return {key: row.get(key) for key in JSON_KEYS}


def classify_row(normalized, min_users, first_party_domains):
    error_id = (normalized.get("error_id") or "").strip()
    error_text = (normalized.get("error_text") or "").strip()
    users, users_warning = parse_int(normalized.get("users"))
    count, _ = parse_int(normalized.get("count"))

    entry = {
        "error_id": error_id,
        "error_text": error_text,
        "severity": (normalized.get("severity") or "").strip(),
        "signal": (normalized.get("signal") or "").strip(),
        "users": users,
        "count": count,
        "teams": (normalized.get("teams") or "").strip(),
        "top_pages": (normalized.get("top_pages") or "").strip(),
        "browsers": (normalized.get("browsers") or "").strip(),
        "eligible": False,
        "skip_reason": None,
        "third_party_signals": [],
        "warnings": [],
    }
    if users_warning:
        entry["warnings"].append(users_warning)

    # Hard 1st-party filter FIRST — never enter the queue on a "suspected" basis.
    signals = third_party_signals(error_text, first_party_domains)
    if signals:
        entry["skip_reason"] = "skipped-3rd-party"
        entry["third_party_signals"] = signals
        return entry

    if users < min_users:
        # fail-closed: unparseable users -> 0 -> below threshold (warning recorded)
        entry["skip_reason"] = "skipped-below-threshold"
        return entry

    entry["eligible"] = True
    return entry


def load_csv_rows(csv_path):
    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not (row.get(COL_ID) or "").strip():
                continue  # blank/trailing rows
            rows.append(normalize_csv_row(row))
    return rows


def load_json_rows(json_path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rows = data.get("rows", data) if isinstance(data, dict) else data
    return [normalize_json_row(row) for row in rows if (row.get("error_id") or "").strip()]


def build_result(input_path, normalized_rows, min_users, first_party_domains):
    classified = [
        classify_row(row, min_users, first_party_domains) for row in normalized_rows
    ]
    queue = sorted(
        (r for r in classified if r["eligible"]),
        key=lambda r: r["users"],
        reverse=True,
    )
    skipped = [r for r in classified if not r["eligible"]]

    return {
        "input_path": str(input_path),
        "min_users": min_users,
        "first_party_domains": first_party_domains,
        "totals": {
            "rows": len(classified),
            "eligible": len(queue),
            "skipped_below_threshold": sum(
                1 for r in skipped if r["skip_reason"] == "skipped-below-threshold"
            ),
            "skipped_3rd_party": sum(
                1 for r in skipped if r["skip_reason"] == "skipped-3rd-party"
            ),
        },
        "queue": queue,
        "skipped": skipped,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", type=Path, nargs="?", help="Dynatrace Error Inspector CSV export")
    ap.add_argument("--json", type=Path, default=None, help="canonical JSON row list (live-pull / token-pull output)")
    ap.add_argument("--min-users", type=int, default=100)
    ap.add_argument("--first-party-domain", action="append", dest="first_party_domains", required=True,
                     help="your site's domain (repeatable for multiple domains) — REQUIRED, no default")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if bool(args.csv_path) == bool(args.json):
        print("provide exactly one of: csv_path, --json", file=sys.stderr)
        return 2

    first_party_domains = args.first_party_domains

    if args.json:
        if not args.json.exists():
            print(f"file not found: {args.json}", file=sys.stderr)
            return 1
        input_path = args.json
        normalized_rows = load_json_rows(args.json)
    else:
        if not args.csv_path.exists():
            print(f"file not found: {args.csv_path}", file=sys.stderr)
            return 1
        input_path = args.csv_path
        normalized_rows = load_csv_rows(args.csv_path)

    result = build_result(input_path, normalized_rows, args.min_users, first_party_domains)

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
        print(
            f"queue written: {args.out} "
            f"({result['totals']['eligible']} eligible / {result['totals']['rows']} rows)",
        )
    else:
        print(output)
    return 0  # empty queue is a valid result


if __name__ == "__main__":
    raise SystemExit(main())
