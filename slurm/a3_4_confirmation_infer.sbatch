#!/bin/bash
#SBATCH --job-name=patchalign-a34-confirm-infer
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-confirm-infer-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 inference failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a3_confirmation_inference_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
ROLE=${CONFIRMATION_ROLE:?submit with CONFIRMATION_ROLE=m0 or m1_r2}
case "${ROLE}" in m0|m1_r2) ;; *) exit 64 ;; esac
OUTPUT=${REPO}/artifacts/a3/confirmation/${ROLE}
PREFLIGHT=${CONFIRMATION_PREFLIGHT:?submit with CONFIRMATION_PREFLIGHT=/absolute/preflight.json}
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
test -f /mingli01/data/patchalign-cpp/a3/confirmation-v1-1/confirmation-manifest.json
test -f "${REPO}/artifacts/a3/sft-r2/training/training-manifest.json"
mkdir -p "${REPO}/artifacts/a3/confirmation" "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_confirmation_inference role=${ROLE} job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/training/run_a3_sft_r2_inference.py \
  --config "${CONFIG}" \
  --role "${ROLE}" \
  --preflight "${PREFLIGHT}" \
  --environment-lock "${ENV_LOCK}" \
  --output-dir "${OUTPUT}" \
  --segment-seconds 27600
date -Is
test -f "${OUTPUT}/run-manifest.json"
sha256sum "${OUTPUT}/predictions.jsonl" "${OUTPUT}/run-manifest.json"
