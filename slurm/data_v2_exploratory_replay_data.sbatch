#!/bin/bash
#SBATCH --job-name=patchalign-dv2-replay-data
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --exclude=gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/data-v2/logs/replay-data-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 replay data failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_exploratory_replay_v0_1.json
OUTPUT=/mingli01/data/patchalign-cpp/data-v2/exploratory-replay-v0.1

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain --untracked-files=no)"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/data-v2/logs" "$(dirname "${OUTPUT}")"

echo "stage=data_v2_exploratory_replay_data"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q tests/unit/test_data_v2_supply_audit.py tests/unit/test_data_v2_exploratory_replay.py
python -u scripts/data/build_data_v2_exploratory_replay.py \
  --config "${CONFIG}" \
  --output-dir "${OUTPUT}"
sha256sum "${OUTPUT}/train.jsonl" "${OUTPUT}/validation.jsonl" \
  "${OUTPUT}/selection-manifest.json" "${OUTPUT}/schema-validation-report.json" \
  "${OUTPUT}/sha256sums.txt"
date -Is
