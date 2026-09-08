#!/bin/bash
#SBATCH --job-name=patchalign-a5-dpo-smoke
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=00:45:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-dpo-smoke-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 DPO GPU smoke failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/training/a5_dpo_v1.json
CPU_PREFLIGHT=${REPO}/artifacts/a5/dpo-preflight-v1/cpu-preflight.json
OUTPUT=${REPO}/artifacts/a5/dpo-preflight-v1/gpu-smoke-work
REPORT=${REPO}/artifacts/a5/dpo-preflight-v1/gpu-smoke.json

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
test ! -e "${OUTPUT}"
test ! -e "${REPORT}"
mkdir -p "${REPO}/artifacts/a5/logs"

printf 'stage=a5_dpo_gpu_smoke job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/training/train_a5_dpo.py \
  --config "${CONFIG}" \
  --cpu-preflight "${CPU_PREFLIGHT}" \
  --variant beta01 \
  --output-dir "${OUTPUT}" \
  --smoke-report "${REPORT}"
sha256sum "${REPORT}"
date -Is
