#!/bin/bash
#SBATCH --job-name=patchalign-a5-final-d4c-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --array=0-175%8
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-final-d4c-score-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "A5 final Defects4C scoring failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
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
test -f "${REPO}/artifacts/a5/final-evaluation-v1/defects4c/inference/run-manifest.json"
printf 'stage=a5_dpo_final_defects4c_scoring index=%s job_id=%s host=%s\n' "${SLURM_ARRAY_TASK_ID}" "${SLURM_JOB_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/evaluation/score_a5_dpo_defects4c_case.py --config "${CONFIG}" --index "${SLURM_ARRAY_TASK_ID}"
date -Is
