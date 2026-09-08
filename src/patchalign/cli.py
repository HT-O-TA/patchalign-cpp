"""Command-line interface for the PatchAlign-Cpp inference demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from patchalign.inference import build_prompt, generate_patch, validate_request


def read_request(path: Path) -> dict:
    return validate_request(json.loads(path.read_text(encoding="utf-8")))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="patchalign-cpp", description="Generate a verified single-file C++ repair patch")
    commands = root.add_subparsers(dest="command", required=True)
    prompt = commands.add_parser("prompt", help="render the frozen repair prompt without loading a model")
    prompt.add_argument("--request", type=Path, required=True)
    infer = commands.add_parser("infer", help="run deterministic NF4 Base+LoRA inference")
    infer.add_argument("--request", type=Path, required=True)
    infer.add_argument("--model-path", type=Path, required=True)
    infer.add_argument("--adapter-path", type=Path, required=True)
    infer.add_argument("--output", type=Path)
    infer.add_argument("--metadata", type=Path)
    infer.add_argument("--seed", type=int, default=20260830)
    infer.add_argument("--max-input-tokens", type=int, default=4096)
    infer.add_argument("--max-new-tokens", type=int, default=512)
    infer.add_argument("--allow-download", action="store_true", help="allow model/tokenizer files not present locally")
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        request = read_request(args.request)
        if args.command == "prompt":
            sys.stdout.write(build_prompt(request))
            return
        result = generate_patch(
            request,
            args.model_path,
            args.adapter_path,
            seed=args.seed,
            max_input_tokens=args.max_input_tokens,
            max_new_tokens=args.max_new_tokens,
            local_files_only=not args.allow_download,
        )
        if args.output:
            args.output.write_text(result["patch"], encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(result["patch"])
        if args.metadata:
            metadata = {key: value for key, value in result.items() if key != "patch"}
            args.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    except Exception as exc:
        print(f"patchalign-cpp: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
