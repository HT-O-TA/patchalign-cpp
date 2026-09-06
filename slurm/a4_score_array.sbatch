#!/bin/bash
#SBATCH --job-name=patchalign-a4-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=3G
#SBATCH --time=12:00:00
#SBATCH --array=0-263%16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a4/logs/a4-score-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "A4 score failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a4_preference_scoring_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -u scripts/preference/score_a4_candidate_case.py --config "${CONFIG}" --case-index "${SLURM_ARRAY_TASK_ID}"
