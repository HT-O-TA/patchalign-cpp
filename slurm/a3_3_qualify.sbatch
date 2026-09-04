#!/bin/bash
#SBATCH --job-name=patchalign-a33-qualify
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a33-qualify-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.3 qualification failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CANDIDATES=/mingli01/data/patchalign-cpp/a3/formal-holdout-candidates-v1
PROGRESS=/mingli01/data/patchalign-cpp/a3/formal-holdout-qualification-v1
HOLDOUT=/mingli01/data/patchalign-cpp/a3/formal-holdout-v1
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
test -f "${CANDIDATES}/candidate-manifest.json"
test ! -e "${HOLDOUT}"
mkdir -p /mingli01/data/patchalign-cpp/a3 "${REPO}/artifacts/a3/logs"

echo "stage=A3.3_formal_holdout_qualification"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q tests/unit/test_a3_formal_data.py
python scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
python -u scripts/data/qualify_a3_formal_holdout.py \
  --candidate-dir "${CANDIDATES}" \
  --progress-dir "${PROGRESS}" \
  --holdout-dir "${HOLDOUT}" \
  --model-path "${MODEL}" \
  --max-input-tokens 4096 \
  --allowed-path main.cpp \
  --bwrap "${BWRAP}" \
  --workers "${SLURM_CPUS_PER_TASK}" \
  --batch-size "${A33_QUALIFY_BATCH_SIZE:-16}"

date -Is
test -f "${HOLDOUT}/a2-manifest.json"
sha256sum "${HOLDOUT}/a2-manifest.json" \
  "${HOLDOUT}/qualification-results.jsonl"
