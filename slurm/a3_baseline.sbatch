#!/bin/bash
#SBATCH --job-name=patchalign-a30-baseline
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=02:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/inference-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.0 inference failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a3_baseline_v1.json
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v3
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
ROLE=${MODEL_ROLE:?submit with --export=ALL,MODEL_ROLE=m0_base-or-external}
RUN_DIR=${REPO}/artifacts/a3/baseline/${ROLE}/${SLURM_JOB_ID}

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r

test "${ROLE}" = m0_base -o "${ROLE}" = external
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -f "${HOLDOUT}/a2-manifest.json"
test -f "${ENV_LOCK}"
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "$(dirname "${RUN_DIR}")"

echo "stage=A3.0_baseline_inference"
echo "role=${ROLE}"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
python --version
python -m pip check
sha256sum "${CONFIG}" "${REPO}/scripts/baseline/run_a3_baseline.py" "$0"   "${HOLDOUT}/a2-manifest.json" "${ENV_LOCK}"

cd "${REPO}"
python -u scripts/baseline/run_a3_baseline.py   --config "${CONFIG}"   --model-role "${ROLE}"   --holdout-dir "${HOLDOUT}"   --environment-lock "${ENV_LOCK}"   --output-dir "${RUN_DIR}"

date -Is
sha256sum "${RUN_DIR}/predictions.jsonl" "${RUN_DIR}/prompts.jsonl"   "${RUN_DIR}/generation-summary.json" "${RUN_DIR}/determinism-probe.json"   "${RUN_DIR}/run-manifest.json"
