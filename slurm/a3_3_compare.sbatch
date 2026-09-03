#!/bin/bash
#SBATCH --job-name=patchalign-a33-compare
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a33-compare-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.3 compare failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
BASE=${REPO}/artifacts/a3/formal
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${BASE}/comparison.json"
echo "stage=A3.3_formal_compare job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/training/compare_a3_formal.py \
  --m0-inference "${BASE}/m0-inference" --m0-score "${BASE}/m0-inference/scoring-v2" \
  --sft-inference "${BASE}/sft-inference" --sft-score "${BASE}/sft-inference/scoring-v2" \
  --quality-gates configs/evaluation/quality_gates_v1.json \
  --output "${BASE}/comparison.json"
date -Is
sha256sum "${BASE}/comparison.json"
