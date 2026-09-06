#!/bin/bash
#SBATCH --job-name=patchalign-dv2-preflight
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --exclude=gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/logs/replay-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 exploratory preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/training/data_v2_exploratory_replay_v0_1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
OUTPUT=${REPO}/artifacts/data-v2/exploratory-replay/preflight-${SLURM_JOB_ID}.json
DATA=/mingli01/data/patchalign-cpp/data-v2/exploratory-replay-v0.1

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
test -f "${DATA}/selection-manifest.json"
test -f "${ENV_LOCK}"
mkdir -p "$(dirname "${OUTPUT}")" "${REPO}/artifacts/data-v2/logs"

echo "stage=data_v2_exploratory_replay_preflight"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/training/check_data_v2_exploratory_replay.py \
  --config "${CONFIG}" \
  --environment-lock "${ENV_LOCK}" \
  --output "${OUTPUT}"
sha256sum "${CONFIG}" "${DATA}/selection-manifest.json" "${OUTPUT}"
date -Is
