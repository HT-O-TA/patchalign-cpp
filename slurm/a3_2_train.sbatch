#!/bin/bash
#SBATCH --job-name=patchalign-a32-train
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a32-train-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.2 train failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/training/a3_sft_pilot_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v3
MODE=${PILOT_MODE:?submit with PILOT_MODE=bf16_lora-or-nf4_qlora}
RUN_DIR=${REPO}/artifacts/a3/sft-pilot/${MODE}/${SLURM_JOB_ID}

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r

test "${MODE}" = bf16_lora -o "${MODE}" = nf4_qlora
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -f "${ENV_LOCK}"
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "$(dirname "${RUN_DIR}")"

echo "stage=A3.2_sft_pilot_train_and_generate"
echo "mode=${MODE}"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
python --version
python -m pip check
sha256sum "${CONFIG}" "${ENV_LOCK}" \
  "${REPO}/scripts/training/train_a3_sft_pilot.py" \
  "${REPO}/scripts/training/run_a3_sft_pilot.py" "$0"

cd "${REPO}"
python -u scripts/training/train_a3_sft_pilot.py \
  --config "${CONFIG}" \
  --mode "${MODE}" \
  --environment-lock "${ENV_LOCK}" \
  --output-dir "${RUN_DIR}"

python -u scripts/training/run_a3_sft_pilot.py \
  --config "${CONFIG}" \
  --mode "${MODE}" \
  --adapter-dir "${RUN_DIR}/adapter" \
  --training-manifest "${RUN_DIR}/training-manifest.json" \
  --holdout-dir "${HOLDOUT}" \
  --environment-lock "${ENV_LOCK}" \
  --output-dir "${RUN_DIR}/inference"

date -Is
sha256sum "${RUN_DIR}/adapter/adapter_model.safetensors" \
  "${RUN_DIR}/training-manifest.json" "${RUN_DIR}/training-summary.json" \
  "${RUN_DIR}/inference/predictions.jsonl" \
  "${RUN_DIR}/inference/generation-summary.json" \
  "${RUN_DIR}/inference/run-manifest.json"
