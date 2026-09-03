#!/bin/bash
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --output=slurm-%j.out

set -euo pipefail

module load conda/3
source /persist_data/apps/miniconda3/etc/profile.d/conda.sh

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v1
RESULT=/mingli01/data/patchalign-cpp/a2/execution-results.jsonl
RAW=/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data
PILOT=/mingli01/data/patchalign-cpp/a1/processed/pilot-v1-stratified

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -d "${REPO}/.git"
test -d "${RAW}"
test -d "${PILOT}"
command -v bwrap >/dev/null

cd "${REPO}"
test -z "$(git status --porcelain)"
if [ ! -f "${HOLDOUT}/a2-manifest.json" ]; then
  python scripts/data/build_a2_holdout.py --raw-dir "${RAW}" --pilot-dir "${PILOT}" --output-dir "${HOLDOUT}"
fi
test -f "${HOLDOUT}/a2-manifest.json"
python -m py_compile scripts/data/run_a2_cases.py
python scripts/data/run_a2_cases.py --holdout-dir "${HOLDOUT}" --output "${RESULT}"
echo "git_commit=$(git rev-parse HEAD)"
echo "result=${RESULT}"
