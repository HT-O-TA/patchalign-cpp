#!/bin/bash
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --output=slurm-%j.out

set -euo pipefail
trap 'rc=$?; echo "A2a command failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
RAW=/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data
PILOT=/mingli01/data/patchalign-cpp/a1/processed/pilot-v1-stratified
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v1

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONNOUSERSITE=1
hash -r

echo "stage=A2a_holdout"
echo "host=$(hostname)"
echo "job_id=${SLURM_JOB_ID:-unknown}"
echo "repo=${REPO}"
echo "raw=${RAW}"
echo "pilot=${PILOT}"
echo "holdout=${HOLDOUT}"

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -d "${REPO}/.git"
test -d "${RAW}"
test -d "${PILOT}"

cd "${REPO}"
test -z "$(git status --porcelain)"
test ! -e "${HOLDOUT}"
python -m py_compile scripts/data/build_a2_holdout.py
python scripts/data/build_a2_holdout.py \
  --raw-dir "${RAW}" \
  --pilot-dir "${PILOT}" \
  --output-dir "${HOLDOUT}"

test -f "${HOLDOUT}/a2-manifest.json"
test -f "${HOLDOUT}/holdout-report.json"
(
  cd "${HOLDOUT}"
  {
    sha256sum a2-manifest.json holdout-report.json
    find cases -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
  } > sha256sums.txt
  sha256sum --quiet --check sha256sums.txt
)

echo "git_commit=$(git rev-parse HEAD)"
echo "manifest_sha256=$(sha256sum "${HOLDOUT}/a2-manifest.json" | cut -d' ' -f1)"
echo "report_sha256=$(sha256sum "${HOLDOUT}/holdout-report.json" | cut -d' ' -f1)"
echo "sha256sums_sha256=$(sha256sum "${HOLDOUT}/sha256sums.txt" | cut -d' ' -f1)"
