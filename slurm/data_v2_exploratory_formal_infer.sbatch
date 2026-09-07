#!/bin/bash
#SBATCH --job-name=patchalign-dv2-formal-infer
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --exclude=gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/logs/formal-infer-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 formal inference failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/data_v2_exploratory_formal_inference_v0_1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
OUTPUT=${REPO}/artifacts/data-v2/exploratory-formal/inference
PREFLIGHT=${DV2_FORMAL_INFERENCE_PREFLIGHT:?submit with DV2_FORMAL_INFERENCE_PREFLIGHT=/absolute/preflight.json}
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -f "${ENV_LOCK}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${PREFLIGHT}"
test -f /mingli01/data/patchalign-cpp/a3/formal-holdout-v1/a2-manifest.json
test -f "${REPO}/artifacts/data-v2/exploratory-replay-training/training-manifest.json"
mkdir -p "${REPO}/artifacts/data-v2/exploratory-formal" "${REPO}/artifacts/data-v2/logs"
echo "stage=data_v2_exploratory_formal_inference job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/training/run_data_v2_exploratory_formal_inference.py \
  --config "${CONFIG}" \
  --role dv2 \
  --preflight "${PREFLIGHT}" \
  --environment-lock "${ENV_LOCK}" \
  --output-dir "${OUTPUT}" \
  --segment-seconds 27600
date -Is
test -f "${OUTPUT}/run-manifest.json"
sha256sum "${OUTPUT}/predictions.jsonl" "${OUTPUT}/run-manifest.json"
