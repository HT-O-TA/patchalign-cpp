#!/bin/bash
#SBATCH --job-name=patchalign-a5-cli-smoke
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --time=00:20:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-cli-smoke-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 delivery CLI smoke failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
MODEL=/mingli01/models/Qwen2.5-Coder-7B
CONFIG=${REPO}/configs/evaluation/a5_dpo_final_v1.json
COMPARISON=${REPO}/artifacts/a5/final-evaluation-v1/comparison.json
REQUEST=${REPO}/examples/repair_request.json
OUTPUT_DIR=${REPO}/artifacts/a5/delivery/cli-smoke-v1
export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${COMPARISON}"
test ! -e "${OUTPUT_DIR}"

recommended=$(python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["recommended_model"])' "${COMPARISON}")
case "${recommended}" in
  dpo_beta03)
    ADAPTER=${REPO}/artifacts/a5/dpo-training-v1.1/beta03/final-adapter
    ;;
  m1_r2)
    ADAPTER=${REPO}/artifacts/a3/sft-r2/training/checkpoints/checkpoint-step-000150-epoch-1/adapter
    ;;
  *)
    echo "unknown recommended model: ${recommended}" >&2
    exit 2
    ;;
esac

mkdir -p "${OUTPUT_DIR}"
printf 'stage=a5_delivery_cli_smoke job_id=%s host=%s recommended_model=%s\n' "${SLURM_JOB_ID}" "$(hostname)" "${recommended}"
date -Is
cd "${REPO}"
python -m patchalign.cli infer \
  --request "${REQUEST}" \
  --model-path "${MODEL}" \
  --adapter-path "${ADAPTER}" \
  --output "${OUTPUT_DIR}/candidate.patch" \
  --metadata "${OUTPUT_DIR}/metadata.json"
python -u scripts/evaluation/summarize_a5_cli_smoke.py \
  --config "${CONFIG}" \
  --comparison "${COMPARISON}" \
  --metadata "${OUTPUT_DIR}/metadata.json" \
  --patch "${OUTPUT_DIR}/candidate.patch" \
  --output "${OUTPUT_DIR}/summary.json" \
  --job-id "${SLURM_JOB_ID}"
sha256sum "${OUTPUT_DIR}/candidate.patch" "${OUTPUT_DIR}/metadata.json" "${OUTPUT_DIR}/summary.json"
date -Is
