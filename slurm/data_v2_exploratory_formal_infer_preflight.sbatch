#!/bin/bash
#SBATCH --job-name=patchalign-dv2-formal-preflight
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --exclude=gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/logs/formal-infer-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 formal inference preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/data_v2_exploratory_formal_inference_v0_1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
OUTPUT=${REPO}/artifacts/data-v2/exploratory-formal/inference
REPORT=${REPO}/artifacts/data-v2/exploratory-formal/inference-preflight-${SLURM_JOB_ID}.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -f "${ENV_LOCK}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/data-v2/exploratory-formal" "${REPO}/artifacts/data-v2/logs"
echo "stage=data_v2_exploratory_formal_inference_preflight job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/training/check_data_v2_exploratory_formal_inference.py \
  --config "${CONFIG}" \
  --environment-lock "${ENV_LOCK}" \
  --output-dir "${OUTPUT}" \
  --report "${REPORT}"
date -Is
sha256sum "${CONFIG}" "${REPORT}"
