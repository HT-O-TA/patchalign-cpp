#!/bin/bash
#SBATCH --job-name=patchalign-a5-dpo
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --array=0-1%2
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-dpo-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "A5 DPO training failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/training/a5_dpo_v1.json
CPU_PREFLIGHT=${REPO}/artifacts/a5/dpo-preflight-v1/cpu-preflight.json
GPU_SMOKE=${REPO}/artifacts/a5/dpo-preflight-v1/gpu-smoke.json
VARIANTS=(beta01 beta03)
VARIANT=${VARIANTS[${SLURM_ARRAY_TASK_ID}]}
OUTPUT=${REPO}/artifacts/a5/dpo-training-v1/${VARIANT}

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
test -f "${CPU_PREFLIGHT}"
test -f "${GPU_SMOKE}"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a5/logs"

printf 'stage=a5_dpo_train variant=%s job_id=%s array_task=%s host=%s\n' "${VARIANT}" "${SLURM_JOB_ID}" "${SLURM_ARRAY_TASK_ID}" "$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/training/train_a5_dpo.py \
  --config "${CONFIG}" \
  --cpu-preflight "${CPU_PREFLIGHT}" \
  --gpu-smoke "${GPU_SMOKE}" \
  --variant "${VARIANT}" \
  --output-dir "${OUTPUT}"
test -f "${OUTPUT}/training-manifest.json"
sha256sum "${OUTPUT}/training-summary.json" "${OUTPUT}/training-manifest.json"
date -Is
