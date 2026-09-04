#!/bin/bash
#SBATCH --job-name=patchalign-a34-data
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-data-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 data build failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
SOURCE=/mingli01/data/patchalign-cpp/a3/formal-sft-v1
OUTPUT=/mingli01/data/patchalign-cpp/a3/sft-r2-data-v1

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${SOURCE}/formal-data-lock.json"
test -f "${SOURCE}/train.jsonl"
test -f "${SOURCE}/validation.jsonl"
test ! -e "${OUTPUT}"
mkdir -p "$(dirname "${OUTPUT}")" "${REPO}/artifacts/a3/logs"

echo "stage=A3.4_sft_r2_data"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q tests/unit/test_a3_sft_r2.py
python -u scripts/data/build_a3_sft_r2_data.py \
  --source-root "${SOURCE}" \
  --output-dir "${OUTPUT}"
sha256sum \
  configs/data/a3_sft_r2_v1.json \
  "${OUTPUT}/train.jsonl" \
  "${OUTPUT}/validation.jsonl" \
  "${OUTPUT}/selection-manifest.json"
date -Is
