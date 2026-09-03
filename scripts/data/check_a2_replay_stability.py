"""Fail unless qualification and final A2 result projections are identical."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .a2_stability import stable_replay
except ImportError:
    from a2_stability import stable_replay


def load(path: Path) -> dict[str, dict[str, Any]]:
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        case_id = str(record["case_id"])
        if case_id in records:
            raise RuntimeError(f"duplicate case_id in {path}: {case_id}")
        records[case_id] = record
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    args = parser.parse_args()
    qualification = load(args.qualification)
    final = load(args.final)
    if set(qualification) != set(final):
        raise SystemExit("stability_failed: qualification/final case sets differ")
    changed = [
        case_id
        for case_id in sorted(qualification)
        if not stable_replay(
            qualification[case_id]["versions"], final[case_id]["versions"]
        )
    ]
    if changed:
        raise SystemExit(
            "stability_failed: execution projections differ for " + ",".join(changed)
        )
    print(json.dumps({"cases": len(final), "stable": True}, sort_keys=True))


if __name__ == "__main__":
    main()
