#!/bin/bash
#SBATCH --job-name=patchalign-a30-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/score-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.0 score failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v3
ROLE=${MODEL_ROLE:?missing MODEL_ROLE}
INFERENCE_JOB_ID=${BASELINE_JOB_ID:?missing BASELINE_JOB_ID}
RUN_DIR=${REPO}/artifacts/a3/baseline/${ROLE}/${INFERENCE_JOB_ID}
SCORE_DIR=${RUN_DIR}/scoring

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "${ROLE}" = m0_base -o "${ROLE}" = external
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -x "${BWRAP}"
test -f "${RUN_DIR}/predictions.jsonl"
test -f "${RUN_DIR}/run-manifest.json"
test ! -e "${SCORE_DIR}"
test -z "$(cd "${REPO}" && git status --porcelain)"

echo "stage=A3.0_baseline_scoring"
echo "role=${ROLE}"
echo "inference_job_id=${INFERENCE_JOB_ID}"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is

cd "${REPO}"
python scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
python -u scripts/baseline/score_a3_baseline.py   --holdout-dir "${HOLDOUT}"   --predictions "${RUN_DIR}/predictions.jsonl"   --inference-manifest "${RUN_DIR}/run-manifest.json"   --bwrap "${BWRAP}"   --output-dir "${SCORE_DIR}"

date -Is
sha256sum "${SCORE_DIR}/scores.jsonl" "${SCORE_DIR}/score-summary.json"   "${SCORE_DIR}/score-manifest.json"
