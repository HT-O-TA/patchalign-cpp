#!/bin/bash
#SBATCH --job-name=patchalign-dv2-content20
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=12:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/github-execution-feasibility-content-%j.out

set -euo pipefail
trap 'rc=$?; echo "GitHub feasibility content failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_github_execution_feasibility_content_v1.json
OUTPUT=${REPO}/artifacts/data-v2/github-executable-evidence-v2/feasibility-content-v1
CONTENT=/mingli01/data/patchalign-cpp/data-v2/github-executable-evidence-v2/feasibility-content-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
for name in content-plan.jsonl decisions.jsonl summary.json run-manifest.json; do
  test ! -e "${OUTPUT}/${name}"
done
AVAILABLE_KB="$(df --output=avail /mingli01/data/patchalign-cpp | tail -1)"
test "${AVAILABLE_KB}" -ge 52428800

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs "${CONTENT}"
printf 'stage=data_v2_github_execution_feasibility_content job_id=%s host=%s authenticated_api=%s available_kb=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)" \
  "$([ -n "${GITHUB_TOKEN:-}" ] && echo true || echo false)" "${AVAILABLE_KB}"
date -Is
python -m pytest -q
python scripts/data/prepare_data_v2_github_execution_feasibility_content.py \
  --config "${CONFIG}" --preflight-only
python -u scripts/data/prepare_data_v2_github_execution_feasibility_content.py \
  --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/content-plan.jsonl" \
  "${OUTPUT}/decisions.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"
