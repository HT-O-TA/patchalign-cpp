#!/bin/bash
#SBATCH --job-name=patchalign-a4-generate
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a4/logs/a4-generate-%j.out

set -euo pipefail
trap 'rc=$?; echo "A4 generation failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/artifacts/a4/generation-config-v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${CONFIG}"
mkdir -p "${REPO}/artifacts/a4/logs"
echo "stage=A4_owner_authorized_exploratory_generation job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/preference/run_a4_candidate_generation.py \
  --config "${CONFIG}" --environment-lock "${ENV_PREFIX}/repro/pip-freeze.txt" \
  --segment-seconds 27600
date -Is
