#!/bin/bash
#SBATCH --job-name=patchalign-dv2-dev-exec
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/data-v2-dev-exec-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 dev execution qualification failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_dev_exec_v1.json
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
OUTPUT=/mingli01/data/patchalign-cpp/data-v2/dev-exec-v1

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -x "${BWRAP}"
test ! -e "${OUTPUT}"

cd "${REPO}"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_dev_exec job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python -u scripts/data/qualify_data_v2_dev_exec.py --config "${CONFIG}" --bwrap "${BWRAP}"
date -Is
sha256sum \
  "${OUTPUT}/dev-exec-manifest.json" \
  "${OUTPUT}/qualification-results.jsonl" \
  "${OUTPUT}/qualification-summary.json"
