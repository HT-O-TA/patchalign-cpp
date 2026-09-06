#!/bin/bash
#SBATCH --job-name=patchalign-a4-preference-finalize
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a4/logs/a4-preference-finalize-%j.out

set -euo pipefail
trap 'rc=$?; echo "A4 preference finalization failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a4_preference_scoring_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -u scripts/preference/finalize_a4_preferences.py --config "${CONFIG}"
sha256sum artifacts/a4/preference-scoring-v1/scores.jsonl artifacts/a4/preference-scoring-v1/preferences.jsonl artifacts/a4/preference-scoring-v1/summary.json artifacts/a4/preference-scoring-v1/run-manifest.json
