#!/bin/bash
#SBATCH --job-name=patchalign-d4c-qualify
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --array=0-202%4
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-qualify-%A_%a.out

set -euo pipefail
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_qualification_v1.json
PREFLIGHT=${DEFECTS4C_PREFLIGHT:?submit with DEFECTS4C_PREFLIGHT=/absolute/report.json}
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1
test -f "${PREFLIGHT}"
test -f /mingli01/data/patchalign-cpp/external/defects4c/runtime/source-progress-v1/download-manifest.json
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -u scripts/external/qualify_defects4c_case.py --config "${CONFIG}" --preflight "${PREFLIGHT}" --index "${SLURM_ARRAY_TASK_ID}"
