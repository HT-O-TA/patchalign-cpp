#!/bin/bash
#SBATCH --job-name=patchalign-g0-smoke
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/smoke/logs/slurm-%j.out

source /etc/profile
set -eo pipefail

module load conda/3
module load cuda/13.0

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
PROJECT_ROOT=/mingli01/project/ht/patchalign-cpp
export PATH="${ENV_PREFIX}/bin:${PATH}"
hash -r

export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

MODEL_PATH=/mingli01/models/Qwen2.5-Coder-7B
RUN_DIR="${PROJECT_ROOT}/artifacts/smoke/g0/${SLURM_JOB_ID}"
SCRIPT_PATH="${PROJECT_ROOT}/scripts/smoke/patchalign_g0_smoke.py"

mkdir -p "${RUN_DIR}"

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"

date -Is
hostname
id -un
nvidia-smi
python --version
python -m pip check
python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'
sha256sum "${SCRIPT_PATH}" "$0" "${MODEL_PATH}/config.json" "${MODEL_PATH}/model.safetensors.index.json"

python -u "${SCRIPT_PATH}" \
  --phase bf16 \
  --model-path "${MODEL_PATH}" \
  --output-dir "${RUN_DIR}"

python -u "${SCRIPT_PATH}" \
  --phase nf4 \
  --model-path "${MODEL_PATH}" \
  --output-dir "${RUN_DIR}"

date -Is
sha256sum "${RUN_DIR}"/*.json "${RUN_DIR}"/*-adapter/adapter_config.json "${RUN_DIR}"/*-adapter/adapter_model.safetensors
