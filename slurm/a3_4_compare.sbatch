#!/bin/bash
#SBATCH --job-name=patchalign-a34-compare
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-compare-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 comparison failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a3_sft_r2_comparison_v1.json
OUTPUT=${REPO}/artifacts/a3/sft-r2/comparison-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_sft_r2_compare job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/training/compare_a3_sft_r2.py --config "${CONFIG}"
date -Is
sha256sum "${OUTPUT}/promotion-vs-m0.json" "${OUTPUT}/diagnostic-vs-m1.json" "${OUTPUT}/comparison-manifest.json"
