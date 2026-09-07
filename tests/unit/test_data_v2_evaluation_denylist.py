from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.data.check_data_v2_evaluation_denylist import (
    compile_identity_sets,
    normalize_repository_name,
    repository_denial_reason,
    sha256_file,
    sha256_identity_set,
    validate_static_config,
)


ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    return json.loads((ROOT / "configs/data/data_v2_evaluation_denylist_v1.json").read_text(encoding="utf-8"))


def test_static_contract_is_complete_only_for_content_acquisition() -> None:
    config = load_config()
    validate_static_config(config)
    assert config["scope"]["complete_for_candidate_content_acquisition"] is True
    assert config["scope"]["exact_content_and_commit_dedup_still_required"] is True
    assert config["scope"]["training_admitted"] is False
    assert config["scope"]["gpu_authorized"] is False
    assert config["scope"]["evaluation_gold_consumed"] is False


def test_repository_alias_normalization_and_denial_layers() -> None:
    config = load_config()
    assert normalize_repository_name("yaml-cpp") == normalize_repository_name("yaml_cpp")
    assert repository_denial_reason("github.com/llvm/llvm-project", config) == "exact_protected_repository"
    assert repository_denial_reason("github.com/someone/yaml-cpp", config) == "protected_repository_alias"
    assert repository_denial_reason("github.com/example/my-leetcode-solutions", config) == "protected_source_domain"
    assert repository_denial_reason("github.com/fresh/safe-project", config) is None


def test_fork_lineage_must_resolve_and_inherits_denial() -> None:
    config = load_config()
    assert repository_denial_reason("github.com/fresh/fork", config, is_fork=True) == "fork_lineage_unresolved"
    assert (
        repository_denial_reason(
            "github.com/fresh/fork",
            config,
            is_fork=True,
            fork_source="github.com/bitcoin/bitcoin",
        )
        == "exact_protected_repository"
    )
    assert (
        repository_denial_reason(
            "github.com/fresh/fork",
            config,
            is_fork=True,
            fork_source="github.com/fresh/upstream",
        )
        is None
    )


def write_manifest(path: Path, identities: list[str], field: str) -> dict:
    path.write_text(json.dumps({"cases": [{field: value} for value in identities]}) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "case_count": len(identities),
        "identity_field": field,
    }


def test_compiler_consumes_only_identity_projection(tmp_path: Path) -> None:
    config = load_config()
    formal = ["p1", "p2"]
    confirmation = ["p3"]
    formal_spec = write_manifest(tmp_path / "formal.json", formal, "problem_id")
    formal_spec.update(
        {
            "unique_identity_count": 2,
            "identity_set_sha256_lf": sha256_identity_set(set(formal)),
        }
    )
    confirmation_spec = write_manifest(tmp_path / "confirmation.json", confirmation, "problem_id")
    confirmation_spec.update(
        {
            "unique_identity_count": 1,
            "identity_set_sha256_lf": sha256_identity_set(set(confirmation)),
        }
    )
    external = ["danmar___cppcheck", "llvm___llvm-project"]
    external_spec = write_manifest(tmp_path / "external.json", external, "project")
    external_spec["expected_unique_identities"] = external
    config["frozen_manifests"] = {
        "formal_holdout": formal_spec,
        "confirmation": confirmation_spec,
        "defects4c": external_spec,
    }
    compiled = compile_identity_sets(config)
    assert compiled["problem_family_sets"]["union_count"] == 3
    assert compiled["problem_family_sets"]["overlap"] == 0
    assert compiled["external_projects"] == external
    serialized = json.dumps(compiled, sort_keys=True)
    assert "p1" not in serialized and "p2" not in serialized and "p3" not in serialized
    assert "prompt" not in serialized and "fixed_code" not in serialized and "reference_patch" not in serialized


def test_compiler_rejects_problem_family_overlap(tmp_path: Path) -> None:
    config = load_config()
    specs = {}
    for name, values in (("formal_holdout", ["same"]), ("confirmation", ["same"])):
        spec = write_manifest(tmp_path / f"{name}.json", values, "problem_id")
        spec.update(
            {
                "unique_identity_count": 1,
                "identity_set_sha256_lf": sha256_identity_set(set(values)),
            }
        )
        specs[name] = spec
    external = ["danmar___cppcheck"]
    external_spec = write_manifest(tmp_path / "external.json", external, "project")
    external_spec["expected_unique_identities"] = external
    specs["defects4c"] = external_spec
    config["frozen_manifests"] = specs
    with pytest.raises(RuntimeError, match="formal/confirmation problem overlap"):
        compile_identity_sets(config)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("scope", "complete_for_candidate_content_acquisition"), False),
        (("scope", "training_admitted"), True),
        (("scope", "gpu_authorized"), True),
        (("frozen_manifests", "formal_holdout", "case_count"), 499),
        (("protected_benchmarks", "bugscpp", "published_defect_count"), 214),
        (("protected_benchmarks", "bugscpp", "project_ids"), []),
        (("protected_benchmarks", "llvm_apr", "revision"), "0" * 40),
        (("repository_matching", "fork_source_and_parent_resolution_required"), False),
        (("repository_matching", "exclude_if_any_normalized_component_contains"), []),
        (("output_directory",), "/tmp/drift"),
    ],
)
def test_static_contract_rejects_drift(path: tuple[str, ...], value: object) -> None:
    config = copy.deepcopy(load_config())
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(RuntimeError):
        validate_static_config(config)
