"""Create the final readiness input binding after external aggregation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
from scripts.training.a3_formal_common import require, sha256_file, write_json

VERSION = "pre-a4-readiness-v1"
INTERNAL_PATH = "/mingli01/project/ht/patchalign-cpp/artifacts/a3/sft-r2/comparison-v1/promotion-vs-m0.json"
INTERNAL_SHA = "sha256:5425feb24a635cdad734756277680803c984ccb06386f3b91d2379d691b81027"
CONFIRMATION_PATH = "/mingli01/project/ht/patchalign-cpp/artifacts/a3/confirmation/comparison-v1.json"
CONFIRMATION_SHA = "sha256:faca13cc9695c011e19ce1b30a28ce7a02c783b65eec4af07d71aecacf9e6094"
EXTERNAL_PATH = "/mingli01/project/ht/patchalign-cpp/artifacts/a3/defects4c/external-v1/comparison.json"
OUTPUT_LEDGER = "/mingli01/project/ht/patchalign-cpp/artifacts/a3/pre-a4-readiness-v1.json"

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-config", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip(), "readiness binding requires a clean worktree")
    require(not args.output_config.exists(), "refusing to overwrite readiness binding")
    external_path = Path(EXTERNAL_PATH)
    require(external_path.is_file(), "external comparison missing")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    require(external["version"] == "a3-defects4c-external-comparison-v1", "wrong external comparison version")
    require(150 <= external["denominator"] <= 203, "external denominator outside frozen bounds")
    require(isinstance(external["external_gate_passed"], bool), "external gate result missing")
    config = {
        "version": VERSION,
        "inputs": {
            "internal": {"path": INTERNAL_PATH, "sha256": INTERNAL_SHA},
            "confirmation": {"path": CONFIRMATION_PATH, "sha256": CONFIRMATION_SHA},
            "external": {"path": EXTERNAL_PATH, "sha256": sha256_file(external_path)},
        },
        "required_gates": {
            "internal_gate_passed": True,
            "supplementary_confirmation_passed": True,
            "external_gate_passed": True,
        },
        "output": OUTPUT_LEDGER,
    }
    args.output_config.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output_config, config)
    print(json.dumps({"output_config": str(args.output_config), "sha256": sha256_file(args.output_config), "external_gate_passed": external["external_gate_passed"]}, sort_keys=True))

if __name__ == "__main__":
    main()
