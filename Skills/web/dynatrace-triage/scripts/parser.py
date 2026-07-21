#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: parser.py <csv_path> <error_id>", file=sys.stderr)
        return 2

    csv_path = Path(sys.argv[1])
    error_id = sys.argv[2]

    if not csv_path.exists():
      print(f"file not found: {csv_path}", file=sys.stderr)
      return 1

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("error.id") == error_id:
                print(json.dumps(row, indent=2, ensure_ascii=False))
                return 0

    print(f"error id not found: {error_id}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
