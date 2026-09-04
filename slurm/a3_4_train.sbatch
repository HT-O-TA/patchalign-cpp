#!/bin/bash
#SBATCH --job-name=patchalign-a34-train
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=05:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-train-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 training failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/training/a3_sft_r2_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
PREFLIGHT=${A34_PREFLIGHT:?submit with A34_PREFLIGHT=/absolute/preflight-report.json}
OUTPUT=${REPO}/artifacts/a3/sft-r2/training

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
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${PREFLIGHT}"
test -f /mingli01/data/patchalign-cpp/a3/sft-r2-data-v1/selection-manifest.json
mkdir -p "$(dirname "${OUTPUT}")" "${REPO}/artifacts/a3/logs"

echo "stage=A3.4_sft_r2_train"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/training/train_a3_sft_r2.py \
  --config "${CONFIG}" \
  --environment-lock "${ENV_LOCK}" \
  --preflight "${PREFLIGHT}" \
  --output-dir "${OUTPUT}" \
  --segment-seconds 16800
date -Is
test -f "${OUTPUT}/training-manifest.json"
sha256sum "${OUTPUT}/training-summary.json" "${OUTPUT}/training-manifest.json"
