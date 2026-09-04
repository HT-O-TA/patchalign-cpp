#!/bin/bash
#SBATCH --job-name=patchalign-d4c-sources
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-sources-%j.out

set -euo pipefail
trap 'rc=$?; echo "Defects4C source preparation failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_sources_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_defects4c_source_preparation job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/external/prepare_defects4c_sources.py --config "${CONFIG}"
date -Is
sha256sum /mingli01/data/patchalign-cpp/external/defects4c/runtime/source-progress-v1/source-plan.json /mingli01/data/patchalign-cpp/external/defects4c/runtime/source-progress-v1/download-manifest.json
