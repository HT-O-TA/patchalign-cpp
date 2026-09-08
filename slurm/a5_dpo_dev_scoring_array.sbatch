#!/bin/bash
#SBATCH --job-name=patchalign-a5-dev-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --array=0-2%3
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-dev-score-%A_%a.out

set -euo pipefail
trap 'rc=$?; echo "A5 dev scoring failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_dev_v1.json
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
ROLES=(baseline beta01 beta03)
ROLE=${ROLES[${SLURM_ARRAY_TASK_ID}]}
OUTPUT=${REPO}/artifacts/a5/dev-evaluation-v1/scoring/${ROLE}

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -x "${BWRAP}"
test -f "${REPO}/artifacts/a5/dev-evaluation-v1/inference/${ROLE}/run-manifest.json"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a5/logs"

printf 'stage=a5_dpo_dev_scoring role=%s job_id=%s array_task=%s host=%s\n' "${ROLE}" "${SLURM_JOB_ID}" "${SLURM_ARRAY_TASK_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/evaluation/score_a5_dpo_dev.py \
  --config "${CONFIG}" \
  --role "${ROLE}" \
  --output-dir "${OUTPUT}"
test -f "${OUTPUT}/run-manifest.json"
sha256sum "${OUTPUT}/scores.jsonl" "${OUTPUT}/summary.json" "${OUTPUT}/run-manifest.json"
date -Is
