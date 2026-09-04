"""Fetch frozen non-LLVM Defects4C revisions on the Slurm host.

Only Git is invoked here. Third-party build and test code runs later, without
network access, inside the frozen Defects4C rootfs.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any

VERSION = "a3-defects4c-sources-v1"
SOURCE_COMMIT = "aecc2cf5f751d7c0894ae7d95ee0b8ae28e77b39"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n" + result.stdout[-4000:])
    return result


def run_with_transient_retry(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    transient = ("Could not resolve host", "Failed to connect", "Connection timed out", "TLS", "HTTP 5")
    for attempt in range(1, 9):
        try:
            return run(command, cwd, timeout)
        except RuntimeError as exc:
            if attempt == 8 or not any(marker in str(exc) for marker in transient):
                raise
            delay = min(5 * (2 ** (attempt - 1)), 60)
            print(json.dumps({"event": "transient_git_retry", "attempt": attempt, "delay_seconds": delay, "command": command[:3]}, sort_keys=True), flush=True)
            time.sleep(delay)
    raise AssertionError("unreachable")


def validate_config(config: dict[str, Any]) -> None:
    if config.get("version") != VERSION:
        raise RuntimeError("wrong Defects4C source contract version")
    if config["official_source"]["git_commit"] != SOURCE_COMMIT:
        raise RuntimeError("official source revision changed")
    if config["selection"] != {
        "prompt_file": "data/single_function_allinone.saved.jsonl",
        "prompt_sha256": "sha256:3ef1b7e0867b8616f6becf48c30c92478a04a3111dba5f6398c2887db87808ff",
        "cpp_extensions": [".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"],
        "training_manifest": "/mingli01/data/patchalign-cpp/a3/formal-sft-v1/dataset-manifest.json",
        "training_manifest_sha256": "sha256:50b0dd1b49a7f14297e2e70871be910673b725ece8de4795938548d256384c02",
        "excluded_training_overlap": ["bblanchon___ArduinoJson", "znc___znc"],
        "expected_projects": 11,
        "expected_unique_pairs": 203,
        "expected_checkout_targets": 203,
    }:
        raise RuntimeError("Defects4C source selection changed")
    download = config["download"]
    if (download["workers"], download["fetch_timeout_seconds"], download["submodule_timeout_seconds"]) != (4, 1200, 1800):
        raise RuntimeError("download execution contract changed")


def discover(source: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    template = source / "defectsc_tpl"
    pairs: dict[tuple[str, str, str], dict[str, Any]] = {}
    projects: set[str] = set()
    for project_path in sorted(template.glob("projects*/**/project.json")):
        project_dir = project_path.parent
        project = json.loads(project_path.read_text(encoding="utf-8"))
        name = project["repo_name"]
        projects.add(name)
        bug_files = sorted(project_dir.glob("*bugs*.json"))
        if not bug_files:
            raise RuntimeError(f"no bug metadata: {name}")
        for bug_file in bug_files:
            for record in json.loads(bug_file.read_text(encoding="utf-8")):
                after, before = record.get("commit_after"), record.get("commit_before")
                if after and before:
                    pairs[(name, after, before)] = {
                        "project": name,
                        "repository": project["main_repo"].removesuffix(".git"),
                        "commit_after": after,
                        "commit_before": before,
                    }
    selection = config["selection"]
    prompt_path = template / selection["prompt_file"]
    if sha256_file(prompt_path) != selection["prompt_sha256"]:
        raise RuntimeError("official Defects4C prompt file changed")
    by_after = {record["commit_after"]: record for record in pairs.values()}
    selected: dict[str, dict[str, Any]] = {}
    for line in prompt_path.read_text(encoding="utf-8").splitlines():
        prompt = json.loads(line)
        sha, separator, filename = prompt["idx"].partition("___")
        if separator and Path(filename).suffix.lower() in selection["cpp_extensions"] and sha in by_after:
            selected[sha] = {**by_after[sha], "prompt_idx": prompt["idx"], "source_file": filename}
    training_manifest = Path(selection["training_manifest"])
    if sha256_file(training_manifest) != selection["training_manifest_sha256"]:
        raise RuntimeError("formal SFT manifest changed")
    training = json.loads(training_manifest.read_text(encoding="utf-8"))
    training_families = {item["repo_family"].lower() for item in training["samples"]}
    overlap = sorted({
        item["project"] for item in selected.values()
        if item["project"].replace("___", "/").lower() in training_families
    })
    if overlap != selection["excluded_training_overlap"]:
        raise RuntimeError(f"external/training family overlap changed: {overlap}")
    records = [selected[key] for key in sorted(selected) if selected[key]["project"] not in overlap]
    projects = {item["project"] for item in records}
    targets = {(item["project"], item["commit_after"]) for item in records}
    expected = config["selection"]
    observed = (len(projects), len(records), len(targets))
    required = (expected["expected_projects"], expected["expected_unique_pairs"], expected["expected_checkout_targets"])
    if observed != required:
        raise RuntimeError(f"Defects4C source denominator changed: {observed} != {required}")
    return records


def validate_checkout(target: Path, record: dict[str, Any]) -> None:
    if not (target / ".git").is_dir():
        raise RuntimeError("checkout has no .git directory")
    for commit in (record["commit_after"], record["commit_before"]):
        run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], target, 60)
    head = run(["git", "rev-parse", "HEAD"], target, 60).stdout.strip()
    if head != record["commit_after"]:
        raise RuntimeError(f"wrong checkout HEAD: {head}")


def download_one(record: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    download = config["download"]
    output, progress = Path(download["output_directory"]), Path(download["progress_directory"])
    key = f"{record['project']}@{record['commit_after']}"
    checkpoint = progress / "checkpoints" / f"{key}.json"
    target = output / record["project"] / f"git_repo_dir_{record['commit_after']}"
    if checkpoint.is_file():
        cached = json.loads(checkpoint.read_text(encoding="utf-8"))
        if cached.get("status") == "completed" and cached.get("record") == record:
            validate_checkout(target, record)
            return cached
    started = time.monotonic()
    result: dict[str, Any] = {"version": VERSION, "key": key, "record": record, "target": str(target), "started_at": utc_now()}
    try:
        target.mkdir(parents=True, exist_ok=True)
        if not (target / ".git").exists():
            run(["git", "init"], target, 60)
        remotes = run(["git", "remote"], target, 60).stdout.split()
        command = (["git", "remote", "set-url", "origin", record["repository"]] if "origin" in remotes else ["git", "remote", "add", "origin", record["repository"]])
        run(command, target, 60)
        for commit in (record["commit_after"], record["commit_before"]):
            run_with_transient_retry(["git", "fetch", "--depth", "1", "origin", commit], target, download["fetch_timeout_seconds"])
        run(["git", "checkout", "-f", "--detach", record["commit_after"]], target, 120)
        run(["git", "submodule", "sync", "--recursive"], target, 120)
        run_with_transient_retry(["git", "submodule", "update", "--init", "--recursive", "--jobs", "1"], target, download["submodule_timeout_seconds"])
        validate_checkout(target, record)
        result["status"] = "completed"
    except BaseException as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    result.update(finished_at=utc_now(), elapsed_seconds=time.monotonic() - started)
    write_json_atomic(checkpoint, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(config)
    source = Path(config["official_source"]["directory"])
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != config["official_source"]["git_commit"]:
        raise RuntimeError(f"official Defects4C source changed: {commit}")
    records = discover(source, config)
    implementation_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
    ).strip()
    progress = Path(config["download"]["progress_directory"])
    Path(config["download"]["output_directory"]).mkdir(parents=True, exist_ok=True)
    progress.mkdir(parents=True, exist_ok=True)
    identity = {"version": VERSION, "config_sha256": sha256_file(args.config), "official_source_commit": commit, "records": records}
    identity_path = progress / "source-plan.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text(encoding="utf-8")) != identity:
            raise RuntimeError("existing source plan differs from frozen contract")
    else:
        write_json_atomic(identity_path, identity)
    results = []
    with ThreadPoolExecutor(max_workers=config["download"]["workers"]) as executor:
        futures = [executor.submit(download_one, record, config) for record in records]
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            print(json.dumps({"event": "source_target_finished", "index": index, "total": len(records), "key": result["key"], "status": result["status"]}, sort_keys=True), flush=True)
    results.sort(key=lambda item: item["key"])
    manifest = {
        "version": VERSION, "created_at": utc_now(), "config_sha256": sha256_file(args.config),
        "official_source_commit": commit, "implementation_git_commit": implementation_commit, "plan_sha256": sha256_file(identity_path),
        "total": len(results), "completed": sum(x["status"] == "completed" for x in results),
        "failed": sum(x["status"] != "completed" for x in results), "results": results,
    }
    write_json_atomic(progress / "download-manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("total", "completed", "failed")}, sort_keys=True))
    if manifest["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
