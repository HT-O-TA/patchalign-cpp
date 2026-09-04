#!/bin/bash
#SBATCH --job-name=patchalign-a33-finalize
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a33-finalize-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.3 finalization failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CP_RAW=/mingli01/data/patchalign-cpp/a1/raw/commitpackft/data/c++/data.jsonl
RBR_RAW=/mingli01/data/patchalign-cpp/a1/raw/runbugrun_data
PILOT=/mingli01/data/patchalign-cpp/a1/processed/pilot-v2-isolated
HOLDOUT=/mingli01/data/patchalign-cpp/a3/formal-holdout-v1
SFT=/mingli01/data/patchalign-cpp/a3/formal-sft-v1
MODEL=/mingli01/models/Qwen2.5-Coder-7B

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${HOLDOUT}/a2-manifest.json"
test ! -e "${SFT}"
mkdir -p "${REPO}/artifacts/a3/formal" "${REPO}/artifacts/a3/logs"

echo "stage=A3.3_formal_data_finalize"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
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
sha256sum "${HOLDOUT}/a2-manifest.json" \
  "${SFT}/dataset-manifest.json" "${SFT}/formal-data-lock.json" \
  "${REPO}/artifacts/a3/formal/preflight-${SLURM_JOB_ID}.json"
