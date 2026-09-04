#!/bin/bash
#SBATCH --job-name=patchalign-pre-a4-finalize
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-pre-a4-finalize-%j.out

set -euo pipefail
trap 'rc=$?; echo "Pre-A4 finalization failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/pre_a4_readiness_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -m pytest -q
python -u scripts/external/finalize_pre_a4_readiness.py --config "${CONFIG}"
sha256sum "${REPO}/artifacts/a3/pre-a4-readiness-v1.json"
