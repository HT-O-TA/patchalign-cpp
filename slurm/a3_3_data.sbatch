#!/bin/bash
#SBATCH --job-name=patchalign-a33-data
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a33-data-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.3 data failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/data/a3_formal_v1.json
CP_RAW=/mingli01/data/patchalign-cpp/a1/raw/commitpackft/data/c++/data.jsonl
RBR_RAW=/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data
PILOT=/mingli01/data/patchalign-cpp/a1/processed/pilot-v2-isolated
CANDIDATES=/mingli01/data/patchalign-cpp/a3/formal-holdout-candidates-v1
PROGRESS=/mingli01/data/patchalign-cpp/a3/formal-holdout-qualification-v1
HOLDOUT=/mingli01/data/patchalign-cpp/a3/formal-holdout-v1
SFT=/mingli01/data/patchalign-cpp/a3/formal-sft-v1
MODEL=/mingli01/models/Qwen2.5-Coder-7B
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -x "${BWRAP}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${HOLDOUT}"
test ! -e "${SFT}"
mkdir -p /mingli01/data/patchalign-cpp/a3 "${REPO}/artifacts/a3/logs"

echo "stage=A3.3_formal_data_build_and_freeze"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
if ! test -f "${CANDIDATES}/candidate-manifest.json"; then
  test ! -e "${CANDIDATES}"
  python -u scripts/data/build_a3_formal_holdout.py \
    --raw-dir "${RBR_RAW}" --pilot-dir "${PILOT}" \
    --output-dir "${CANDIDATES}" \
    --function-candidates 900 --file-window-candidates 250 \
    --required-function 400 --required-file-window 100
fi
python -u scripts/data/qualify_a3_formal_holdout.py \
  --candidate-dir "${CANDIDATES}" --holdout-dir "${HOLDOUT}" \
  --progress-dir "${PROGRESS}" --bwrap "${BWRAP}" \
  --model-path "${MODEL}" --max-input-tokens 4096 --allowed-path main.cpp \
  --workers "${SLURM_CPUS_PER_TASK}" --batch-size "${A33_QUALIFY_BATCH_SIZE:-16}"
python -u scripts/data/build_a3_formal_sft_data.py \
  --commitpack-file "${CP_RAW}" --runbugrun-dir "${RBR_RAW}" \
  --pilot-dir "${PILOT}" --holdout-dir "${HOLDOUT}" \
  --model-path "${MODEL}" --output-dir "${SFT}"
python -u scripts/training/freeze_a3_formal_data.py \
  --config configs/training/a3_sft_formal_v1.json
python -u scripts/training/check_a3_formal.py \
  --config configs/training/a3_sft_formal_v1.json \
  --environment-lock "${ENV_PREFIX}/repro/pip-freeze.txt" \
  --output "${REPO}/artifacts/a3/formal/preflight-${SLURM_JOB_ID}.json"

date -Is
sha256sum "${CONFIG}" "${HOLDOUT}/a2-manifest.json" \
  "${SFT}/dataset-manifest.json" "${SFT}/formal-data-lock.json"
