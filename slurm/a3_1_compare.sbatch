#!/bin/bash
#SBATCH --job-name=patchalign-a31-compare
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=2G
#SBATCH --time=00:20:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a31-compare-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.1 comparison failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
M0_SCORE_JOB_ID=${M0_SCORE_JOB_ID:?missing M0_SCORE_JOB_ID}
EXTERNAL_SCORE_JOB_ID=${EXTERNAL_SCORE_JOB_ID:?missing EXTERNAL_SCORE_JOB_ID}
M0_DIR=${REPO}/artifacts/a3/baseline/m0_base/93717/scoring-v2/${M0_SCORE_JOB_ID}
EXTERNAL_DIR=${REPO}/artifacts/a3/baseline/external/93718/scoring-v2/${EXTERNAL_SCORE_JOB_ID}
OUTPUT_DIR=${REPO}/artifacts/a3/comparison-a31/${SLURM_JOB_ID}

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -f "${M0_DIR}/score-manifest.json"
test -f "${EXTERNAL_DIR}/score-manifest.json"
test ! -e "${OUTPUT_DIR}"
test -z "$(cd "${REPO}" && git status --porcelain)"

echo "stage=A3.1_terminal_lf_comparison"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is

cd "${REPO}"
python scripts/baseline/compare_a3_1_rescores.py \
  --m0-score-dir "${M0_DIR}" \
  --external-score-dir "${EXTERNAL_DIR}" \
  --output "${OUTPUT_DIR}/comparison.json"

date -Is
sha256sum "${OUTPUT_DIR}/comparison.json"
