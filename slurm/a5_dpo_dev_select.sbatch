#!/bin/bash
#SBATCH --job-name=patchalign-a5-dev-select
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-dev-select-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 dev selection failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_dev_v1.json
OUTPUT=${REPO}/artifacts/a5/dev-evaluation-v1/selection.json

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a5/logs"

printf 'stage=a5_dpo_dev_selection job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/evaluation/select_a5_dpo_dev.py --config "${CONFIG}"
sha256sum "${OUTPUT}"
date -Is
