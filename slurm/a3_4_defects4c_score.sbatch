#!/bin/bash
#SBATCH --job-name=patchalign-d4c-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-score-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "Defects4C paired score failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_external_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -n "${SLURM_ARRAY_TASK_ID:-}"
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -u scripts/external/score_defects4c_case.py --config "${CONFIG}" --index "${SLURM_ARRAY_TASK_ID}"
