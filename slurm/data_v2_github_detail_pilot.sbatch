#!/bin/bash
#SBATCH --job-name=patchalign-dv2-detail
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=12:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/github-detail-pilot-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 GitHub detail pilot failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_github_detail_pilot_v1.json
OUTPUT=${REPO}/artifacts/data-v2/github-detail-pilot-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
for name in qualified-metadata.jsonl summary.json run-manifest.json; do
  test ! -e "${OUTPUT}/${name}"
done

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_github_detail_pilot job_id=%s host=%s authenticated_api=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)" "$([ -n "${GITHUB_TOKEN:-}" ] && echo true || echo false)"
date -Is
python -m pytest -q
python -u scripts/data/collect_data_v2_github_detail_pilot.py --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/selected-candidates.jsonl" \
  "${OUTPUT}/qualified-metadata.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"
