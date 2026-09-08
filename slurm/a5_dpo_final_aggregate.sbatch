#!/bin/bash
#SBATCH --job-name=patchalign-a5-final-aggregate
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-final-aggregate-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 final aggregation failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_final_v1.json
export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
printf 'stage=a5_dpo_final_aggregate job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/evaluation/aggregate_a5_dpo_final.py --config "${CONFIG}"
sha256sum "${REPO}/artifacts/a5/final-evaluation-v1/comparison.json" "${REPO}/artifacts/a5/final-evaluation-v1/failure-analysis.json"
date -Is
