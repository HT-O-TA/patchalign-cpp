#!/bin/bash
#SBATCH --job-name=patchalign-d4c-infer-preflight
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-infer-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "Defects4C inference preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_external_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
REPORT=${REPO}/artifacts/a3/defects4c/inference-preflight-${SLURM_JOB_ID}.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "${REPO}/artifacts/a3/defects4c" "${REPO}/artifacts/a3/logs"
cd "${REPO}"
python -m pytest -q
python -u scripts/external/check_defects4c_inference.py --config "${CONFIG}" --environment-lock "${ENV_LOCK}" --report "${REPORT}"
sha256sum "${REPORT}"
