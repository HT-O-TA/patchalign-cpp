#!/bin/bash
#SBATCH --job-name=patchalign-a33-infer
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a33-infer-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.3 inference failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/training/a3_sft_formal_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
ROLE=${FORMAL_ROLE:?submit with FORMAL_ROLE=m0-or-sft}
BASE=${REPO}/artifacts/a3/formal
OUTPUT=${BASE}/${ROLE}-inference
TRAIN=${BASE}/sft-training
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r
test "${ROLE}" = m0 -o "${ROLE}" = sft
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f /mingli01/data/patchalign-cpp/a3/formal-sft-v1/formal-data-lock.json
if test "${ROLE}" = sft; then test -f "${TRAIN}/training-manifest.json"; fi
mkdir -p "${BASE}" "${REPO}/artifacts/a3/logs"
echo "stage=A3.3_formal_inference role=${ROLE} job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
args=(--config "${CONFIG}" --role "${ROLE}" --environment-lock "${ENV_LOCK}" --output-dir "${OUTPUT}" --segment-seconds 27600)
if test "${ROLE}" = sft; then args+=(--training-dir "${TRAIN}"); fi
python -u scripts/training/run_a3_formal_inference.py "${args[@]}"
date -Is
test -f "${OUTPUT}/run-manifest.json"
sha256sum "${OUTPUT}/predictions.jsonl" "${OUTPUT}/run-manifest.json"
