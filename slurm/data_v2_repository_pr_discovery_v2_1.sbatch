#!/bin/bash
#SBATCH --job-name=patchalign-dv2-repo-pr21
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/repository-pr-discovery-v2-1-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 repository/PR discovery v2.1 failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_repository_pr_discovery_v2_1.json
OUTPUT=${REPO}/artifacts/data-v2/repository-pr-discovery-v2-1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
for name in repository-pool.jsonl selected-repositories.jsonl candidates.jsonl summary.json run-manifest.json; do
  test ! -e "${OUTPUT}/${name}"
done

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_repository_pr_discovery_v2_1 job_id=%s host=%s authenticated_api=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)" "$([ -n "${GITHUB_TOKEN:-}" ] && echo true || echo false)"
date -Is
python -m pytest -q
python -u scripts/data/discover_data_v2_repository_prs.py --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/repository-pool.jsonl" \
  "${OUTPUT}/selected-repositories.jsonl" \
  "${OUTPUT}/candidates.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"

