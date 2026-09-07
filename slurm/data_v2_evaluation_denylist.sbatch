#!/bin/bash
#SBATCH --job-name=patchalign-dv2-denylist
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/evaluation-denylist-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 denylist compilation failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_evaluation_denylist_v1.json
OUTPUT=${REPO}/artifacts/data-v2/evaluation-denylist-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}/compiled-identities.json"
test ! -e "${OUTPUT}/run-manifest.json"

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_evaluation_denylist job_id=%s host=%s gpu_requested=false\n' \
  "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python scripts/data/check_data_v2_evaluation_denylist.py --config "${CONFIG}"
date -Is
sha256sum "${OUTPUT}/compiled-identities.json" "${OUTPUT}/run-manifest.json"
