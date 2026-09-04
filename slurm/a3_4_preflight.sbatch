#!/bin/bash
#SBATCH --job-name=patchalign-a34-preflight
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/training/a3_sft_r2_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
OUTPUT=${REPO}/artifacts/a3/sft-r2/preflight-${SLURM_JOB_ID}.json

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
test -f /mingli01/data/patchalign-cpp/a3/sft-r2-data-v1/selection-manifest.json
test -f "${ENV_LOCK}"
mkdir -p "$(dirname "${OUTPUT}")" "${REPO}/artifacts/a3/logs"

echo "stage=A3.4_sft_r2_preflight"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/training/check_a3_sft_r2.py \
  --config "${CONFIG}" \
  --environment-lock "${ENV_LOCK}" \
  --output "${OUTPUT}"
sha256sum "${CONFIG}" "${OUTPUT}"
date -Is
