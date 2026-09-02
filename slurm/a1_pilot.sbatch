#!/bin/bash
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=8
#SBATCH --output=slurm-%j.out

set -euo pipefail

module load conda/3
module load cuda/13.0
source /persist_data/apps/miniconda3/etc/profile.d/conda.sh

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
RAW_COMMITPACK=/mingli01/data/patchalign-cpp/a1/raw/commitpackft
RAW_RUNBUGRUN=/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data
OUTPUT=/mingli01/data/patchalign-cpp/a1/processed/pilot-v1-stratified

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
echo "output=${OUTPUT}"
