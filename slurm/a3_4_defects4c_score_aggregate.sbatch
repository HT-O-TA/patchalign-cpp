#!/bin/bash
#SBATCH --job-name=patchalign-d4c-score-aggregate
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-score-aggregate-%j.out

set -euo pipefail
trap 'rc=$?; echo "Defects4C score aggregation failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_external_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -m pytest -q
python -u scripts/external/aggregate_defects4c_scores.py --config "${CONFIG}"
sha256sum "${REPO}/artifacts/a3/defects4c/external-v1/"*.json "${REPO}/artifacts/a3/defects4c/external-v1/"*.jsonl
