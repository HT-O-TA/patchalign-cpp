#!/bin/bash
#SBATCH --job-name=patchalign-dv2-select20
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:20:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/github-execution-feasibility-selection-%j.out

set -euo pipefail
trap 'rc=$?; echo "GitHub feasibility selection failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_github_execution_feasibility_selection_v1.json
OUTPUT=${REPO}/artifacts/data-v2/github-executable-evidence-v2/feasibility-selection-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_github_execution_feasibility_selection job_id=%s host=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python scripts/data/build_data_v2_github_execution_feasibility_selection.py \
  --config "${CONFIG}"
date -Is
sha256sum "${OUTPUT}"/*
