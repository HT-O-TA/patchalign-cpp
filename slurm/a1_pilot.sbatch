#!/bin/bash
#SBATCH --job-name=patchalign-a1-isolated-v2
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=4G
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=2
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a1-isolated-v2-%j.out

set -euo pipefail
trap 'rc=$?; echo "A1 isolated rebuild failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
RAW_COMMITPACK=/mingli01/data/patchalign-cpp/a1/raw/commitpackft
RAW_RUNBUGRUN=/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data
OUTPUT=/mingli01/data/patchalign-cpp/a1/processed/pilot-v2-isolated

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -d "${REPO}/.git"
test -f "${RAW_COMMITPACK}/data/c++/data.jsonl"
test -f "${RAW_RUNBUGRUN}/cpp_train0.jsonl.gz"
test -f "${RAW_RUNBUGRUN}/cpp_valid0.jsonl.gz"

cd "${REPO}"
test -z "$(git status --porcelain)"
EXPECTED_COMMIT="$(git rev-parse HEAD)"
python -m py_compile scripts/data/build_a1_pilot.py

python scripts/data/build_a1_pilot.py \
  --commitpack-file "${RAW_COMMITPACK}/data/c++/data.jsonl" \
  --runbugrun-dir "${RAW_RUNBUGRUN}" \
  --output-dir "${OUTPUT}"

python - "${OUTPUT}/schema-validation-report.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["sample_count"] == 350, report
assert report["valid_count"] == 350, report
assert report["invalid_count"] == 0, report
print(json.dumps({"schema_report": report}, sort_keys=True))
PY

echo "git_commit=${EXPECTED_COMMIT}"
sha256sum "${OUTPUT}"/*.json "${OUTPUT}"/*.jsonl "${OUTPUT}/sha256sums.txt"

echo "output=${OUTPUT}"
