#!/bin/bash
#SBATCH --job-name=patchalign-a5-final-infer
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --array=0-2%3
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-final-infer-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "A5 final inference failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_final_v1.json
PREFLIGHT=${REPO}/artifacts/a5/final-evaluation-v1/preflight.json
DATASETS=(formal confirmation defects4c)
DATASET=${DATASETS[${SLURM_ARRAY_TASK_ID}]}
OUTPUT=${REPO}/artifacts/a5/final-evaluation-v1/${DATASET}/inference
export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${PREFLIGHT}"
mkdir -p "${REPO}/artifacts/a5/logs"
printf 'stage=a5_dpo_final_inference dataset=%s job_id=%s array_task=%s host=%s\n' "${DATASET}" "${SLURM_JOB_ID}" "${SLURM_ARRAY_TASK_ID}" "$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/evaluation/run_a5_dpo_final_inference.py --config "${CONFIG}" --dataset "${DATASET}" --preflight "${PREFLIGHT}" --output-dir "${OUTPUT}" --segment-seconds 27600
test -f "${OUTPUT}/run-manifest.json"
sha256sum "${OUTPUT}/predictions.jsonl" "${OUTPUT}/generation-summary.json" "${OUTPUT}/run-manifest.json"
date -Is
