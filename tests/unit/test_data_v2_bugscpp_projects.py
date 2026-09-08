from __future__ import annotations

from scripts.data.audit_data_v2_bugscpp_projects import (
    canonical_repository_url,
    expected_split,
)


def registry() -> list[dict]:
    counts = {
        "berry": 5, "coreutils": 2, "cpp_peglib": 10, "cppcheck": 30,
        "dlt_daemon": 1, "example": 1, "exiv2": 20, "jerryscript": 11,
        "libchewing": 8, "libssh": 1, "libtiff": 5, "libtiff_sanitizer": 4,
        "libucl": 6, "libxml2": 7, "md4c": 10, "ndpi": 4, "openssl": 28,
        "proj": 28, "wget2": 3, "wireshark": 6, "xbps": 5,
        "yaml_cpp": 10, "yara": 5, "zsh": 5,
    }
    excluded = {"cppcheck", "example"}
    return [
        {"id": key, "defects": value, "split": "excluded" if key in excluded else "placeholder"}
        for key, value in counts.items()
    ]


def test_repository_url_normalization_is_host_aware() -> None:
    assert canonical_repository_url("https://github.com/Owner/Repo.git") == "github.com/owner/repo"
    assert canonical_repository_url("https://gitlab.gnome.org/GNOME/libxml2.git") == "gitlab.gnome.org/gnome/libxml2"
    assert canonical_repository_url("ssh://github.com/Owner/Repo") is None


def test_preregistered_split_is_deterministic_and_matches_adr() -> None:
    result = expected_split(registry(), 20260908)
    assert {key for key, value in result.items() if value == "heldout"} == {
        "xbps", "libxml2", "libucl", "coreutils", "cpp_peglib", "ndpi", "libtiff",
    }
    assert {key for key, value in result.items() if value == "validation"} == {
        "proj", "yara", "libchewing",
    }
    assert sum(1 for value in result.values() if value == "train") == 12


def test_split_defect_totals_are_fixed_before_license_results() -> None:
    rows = registry()
    mapping = expected_split(rows, 20260908)
    counts = {row["id"]: row["defects"] for row in rows}
    totals = {
        split: sum(counts[key] for key, value in mapping.items() if value == split)
        for split in ("train", "validation", "heldout")
    }
    assert totals == {"train": 104, "validation": 41, "heldout": 39}
    assert sum(row["defects"] for row in rows if row["split"] == "excluded") == 31
