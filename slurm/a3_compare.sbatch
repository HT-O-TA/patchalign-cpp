#!/bin/bash
#SBATCH --job-name=patchalign-a30-compare
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/compare-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.0 comparison failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
M0_ID=${M0_BASELINE_JOB_ID:?missing M0_BASELINE_JOB_ID}
EXTERNAL_ID=${EXTERNAL_BASELINE_JOB_ID:?missing EXTERNAL_BASELINE_JOB_ID}
M0_DIR=${REPO}/artifacts/a3/baseline/m0_base/${M0_ID}
EXTERNAL_DIR=${REPO}/artifacts/a3/baseline/external/${EXTERNAL_ID}
OUTPUT_DIR=${REPO}/artifacts/a3/comparison/${SLURM_JOB_ID}

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -f "${M0_DIR}/scoring/score-summary.json"
test -f "${EXTERNAL_DIR}/scoring/score-summary.json"
test ! -e "${OUTPUT_DIR}"
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "${OUTPUT_DIR}"

echo "stage=A3.0_baseline_comparison"
echo "m0_inference_job_id=${M0_ID}"
echo "external_inference_job_id=${EXTERNAL_ID}"
echo "job_id=${SLURM_JOB_ID}"
date -Is

cd "${REPO}"
python scripts/baseline/compare_a3_baselines.py   --m0-dir "${M0_DIR}"   --external-dir "${EXTERNAL_DIR}"   --output "${OUTPUT_DIR}/comparison.json"

date -Is
sha256sum "${OUTPUT_DIR}/comparison.json"
