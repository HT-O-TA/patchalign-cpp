#!/bin/bash
#SBATCH --job-name=patchalign-d4c-preflight
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-preflight-%j.out

set -euo pipefail
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_qualification_v1.json
REPORT=${REPO}/artifacts/a3/defects4c/qualification-preflight-${SLURM_JOB_ID}.json
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "${REPO}/artifacts/a3/defects4c" "${REPO}/artifacts/a3/logs"
cd "${REPO}"
python -m pytest -q
python -u scripts/external/check_defects4c_qualification.py --config "${CONFIG}" --report "${REPORT}"
sha256sum "${REPORT}"
