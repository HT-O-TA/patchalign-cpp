#!/bin/bash
#SBATCH --job-name=patchalign-a34-confirm-build
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-confirm-build-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 confirmation build failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/data/a3_confirmation_v1.json
OUTPUT=/mingli01/data/patchalign-cpp/a3/confirmation-candidates-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_confirmation_build job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/data/build_a3_confirmation.py --config "${CONFIG}"
date -Is
sha256sum "${OUTPUT}/candidate-manifest.json" "${OUTPUT}/candidate-report.json" "${OUTPUT}/sha256sums.txt"
