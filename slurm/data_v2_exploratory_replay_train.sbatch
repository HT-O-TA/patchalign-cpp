#!/bin/bash
#SBATCH --job-name=patchalign-dv2-replay
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --exclude=gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/logs/replay-train-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 exploratory training failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/training/data_v2_exploratory_replay_v0_1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
PREFLIGHT=${DV2_PREFLIGHT:?submit with DV2_PREFLIGHT=/absolute/preflight-report.json}
OUTPUT=${REPO}/artifacts/data-v2/exploratory-replay-training
DATA=/mingli01/data/patchalign-cpp/data-v2/exploratory-replay-v0.1

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
test -f "${DATA}/selection-manifest.json"
test -f "${ENV_LOCK}"
mkdir -p "${OUTPUT}" "${REPO}/artifacts/data-v2/logs"

echo "stage=data_v2_exploratory_replay_train"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/training/train_data_v2_exploratory_replay.py \
  --config "${CONFIG}" \
  --environment-lock "${ENV_LOCK}" \
  --preflight "${PREFLIGHT}" \
  --output-dir "${OUTPUT}" \
  --segment-seconds 13200
date -Is
test -f "${OUTPUT}/training-manifest.json"
sha256sum "${OUTPUT}/training-summary.json" "${OUTPUT}/training-manifest.json"
