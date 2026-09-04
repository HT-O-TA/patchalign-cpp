"""Run one Defects4C reproduce workflow inside the offline frozen rootfs."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
from typing import Any
from jinja2 import Environment, FileSystemLoader

SOURCE_ROOT = Path("/src")
OUTPUT_ROOT = Path("/out")


def load_metadata(project: str, sha: str) -> tuple[str, Path, dict[str, Any], dict[str, Any]]:
    for version in ("projects", "projects_v1"):
        project_dir = SOURCE_ROOT / version / project
        if not project_dir.is_dir():
            continue
        project_meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        matches: dict[str, dict[str, Any]] = {}
        for path in sorted(project_dir.glob("*bugs*.json")):
            for record in json.loads(path.read_text(encoding="utf-8")):
                if record.get("commit_after") == sha:
                    matches[json.dumps(record, sort_keys=True)] = record
        if len(matches) != 1:
            raise RuntimeError(f"bug metadata not unique: {project}@{sha} count={len(matches)}")
        return version, project_dir, project_meta, next(iter(matches.values()))
    raise RuntimeError(f"unknown project: {project}")


def apt_function() -> str:
    return """apt_install_fn() {
    library=$1
    if dpkg -s "$library" >/dev/null 2>&1 || command -v "$library" >/dev/null 2>&1; then
        return 0
    fi
    echo "offline qualification: missing dependency $library" >&2
    return 1
}
"""


def merged_info(
    project: str,
    sha: str,
    project_meta: dict[str, Any],
    defect: dict[str, Any],
    cpu_count: int,
) -> dict[str, Any]:
    project_compile = project_meta.get("c_compile") or {}
    defect_compile = defect.get("c_compile") or {}
    info = {
        **project_meta,
        **project_compile,
        **{key: value for key, value in defect_compile.items() if value not in (None, [], "")},
        **defect,
    }
    info.update(
        apt_install_fn=apt_function(),
        cpu_count=cpu_count,
        repo_dir=str(OUTPUT_ROOT / project / f"git_repo_dir_{sha}"),
        log_dir=str(OUTPUT_ROOT / project / "logs"),
        build_dir=f"build_{sha}",
        test_log=str(OUTPUT_ROOT / project / "logs" / f"test_{sha}_fix.log"),
        test_files=(defect.get("files") or {}).get("test") or [],
        src_file=((defect.get("files") or {}).get("src") or [None])[0],
        build_flags=(project_compile.get("build_flags") or []) + (defect_compile.get("build_flags") or []),
        test_flags=(project_compile.get("test_flags") or []) + (defect_compile.get("test_flags") or []),
        env=(project_meta.get("env") or []) + (defect_compile.get("env") or []),
    )
    if not info["src_file"]:
        raise RuntimeError("defect has no source file")
    return info


def template_path(version: str, project_dir: Path, info: dict[str, Any], kind: str) -> Path:
    value = str(info.get(kind) or "")
    if ".jinja" in value:
        return project_dir / value
    return SOURCE_ROOT / version / f"common_{kind}_tpl.jinja"


def render(template: Path, values: dict[str, Any], destination: Path) -> None:
    if not template.is_file():
        raise RuntimeError(f"missing template: {template}")
    environment = Environment(loader=FileSystemLoader(str(template.parent)))
    destination.write_text(
        environment.get_template(template.name).render(**values),
        encoding="utf-8",
    )
    destination.chmod(0o700)


def status(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return path.read_text(encoding="utf-8", errors="replace").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--cpu-count", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    args = parser.parse_args()
    if args.cpu_count < 1 or args.timeout_seconds < 60:
        raise SystemExit(64)

    version, project_dir, project_meta, defect = load_metadata(args.project, args.sha)
    info = merged_info(args.project, args.sha, project_meta, defect, args.cpu_count)
    repo = Path(info["repo_dir"])
    logs = Path(info["log_dir"])
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"source checkout missing: {repo}")
    logs.mkdir(parents=True, exist_ok=True)

    subprocess.run(["git", "clean", "-dfx"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    subprocess.run(["git", "checkout", "-f", "--detach", defect["commit_after"]], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    subprocess.run(["git", "submodule", "update", "--init", "--recursive", "--jobs", "1"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    build_template = template_path(version, project_dir, info, "build")
    test_template = template_path(version, project_dir, info, "test")
    rebuild = {**info, "is_rebuild": True, "test_log": info["test_log"]}
    workflow = (
        SOURCE_ROOT / "projects" / "workflow_tpl.jinja"
        if version == "projects"
        else SOURCE_ROOT / "projects_v1" / "workflow_cmake_tpl.jinja"
    )
    render(build_template, info, repo / "inplace_build.sh")
    render(build_template, rebuild, repo / "inplace_rebuild.sh")
    render(test_template, info, repo / "inplace_test.sh")
    render(workflow, info, repo / "run_reproduce.sh")

    log_path = logs / f"qualification_{args.sha}.log"
    timed_out = False
    returncode = None
    error = None
    try:
        with log_path.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                ["bash", "run_reproduce.sh"],
                cwd=repo,
                text=True,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=args.timeout_seconds,
            )
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        error = "reproduce_timeout"

    fixed_status = status(logs / f"test_{args.sha}_fix.status")
    buggy_status = status(logs / f"test_{args.sha}_buggy.status")
    fixed_passed = fixed_status.lower().startswith("success")
    buggy_failed = buggy_status.lower().startswith("failed")
    qualified = not timed_out and returncode == 0 and fixed_passed and buggy_failed
    build_path = repo / info["build_dir"]
    shutil.rmtree(build_path, ignore_errors=True)
    result = {
        "version": "a3-defects4c-rootfs-case-v1",
        "project": args.project,
        "commit_after": args.sha,
        "commit_before": defect["commit_before"],
        "src_file": info["src_file"],
        "returncode": returncode,
        "timed_out": timed_out,
        "error": error,
        "fixed_status": fixed_status,
        "buggy_status": buggy_status,
        "fixed_passed": fixed_passed,
        "buggy_failed": buggy_failed,
        "qualified": qualified,
        "build_directory_removed": not build_path.exists(),
        "log_path": str(log_path),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
