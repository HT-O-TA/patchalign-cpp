#!/bin/bash
#SBATCH --job-name=patchalign-a5-final-cpp-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --array=0-1%2
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-final-cpp-score-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "A5 final C++ scoring failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_final_v1.json
SCORING_CONFIG=${REPO}/configs/evaluation/a3_scoring_v2.json
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
DATASETS=(formal confirmation)
ROOTS=(/mingli01/data/patchalign-cpp/a3/formal-holdout-v1 /mingli01/data/patchalign-cpp/a3/confirmation-v1-1)
MANIFESTS=(a2-manifest.json confirmation-manifest.json)
DATASET=${DATASETS[${SLURM_ARRAY_TASK_ID}]}
HOLDOUT=${ROOTS[${SLURM_ARRAY_TASK_ID}]}
MANIFEST=${MANIFESTS[${SLURM_ARRAY_TASK_ID}]}
INFERENCE=${REPO}/artifacts/a5/final-evaluation-v1/${DATASET}/inference
OUTPUT=${REPO}/artifacts/a5/final-evaluation-v1/${DATASET}/scoring
export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -x "${BWRAP}"
test -f "${INFERENCE}/run-manifest.json"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a5/logs"
printf 'stage=a5_dpo_final_cpp_scoring dataset=%s job_id=%s array_task=%s host=%s\n' "${DATASET}" "${SLURM_JOB_ID}" "${SLURM_ARRAY_TASK_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/baseline/score_a3_baseline.py --holdout-dir "${HOLDOUT}" --predictions "${INFERENCE}/predictions.jsonl" --inference-manifest "${INFERENCE}/run-manifest.json" --bwrap "${BWRAP}" --scoring-config "${SCORING_CONFIG}" --output-dir "${OUTPUT}" --manifest-name "${MANIFEST}"
sha256sum "${OUTPUT}/scores.jsonl" "${OUTPUT}/score-summary.json" "${OUTPUT}/score-manifest.json"
date -Is
