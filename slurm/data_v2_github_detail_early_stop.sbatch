#!/bin/bash
#SBATCH --job-name=patchalign-dv2-stop
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:20:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/github-detail-early-stop-%j.out

set -euo pipefail
trap 'rc=$?; echo "Data-v2 early-stop audit failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_github_detail_early_stop_v1.json
OUTPUT=${REPO}/artifacts/data-v2/github-detail-pilot-v1/early-stop-audit-v1
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_github_detail_early_stop job_id=%s host=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)"
SOURCE_JOB_RECORD="$(
  sacct -X -j 96959 --noheader --parsable2 \
    --format=JobIDRaw,State,ExitCode,Elapsed,Start,End,NodeList
)"
EXPECTED_SOURCE_JOB_RECORD='96959|CANCELLED by 1039|0:0|04:10:31|2026-09-07T13:21:16|2026-09-07T17:31:47|gpu25'
test "${SOURCE_JOB_RECORD}" = "${EXPECTED_SOURCE_JOB_RECORD}"
printf "source_job_record=%s\n" "${SOURCE_JOB_RECORD}"
date -Is
python -m pytest -q
python scripts/data/audit_data_v2_github_detail_early_stop.py \
  --config "${CONFIG}" --preflight-only
python scripts/data/audit_data_v2_github_detail_early_stop.py --config "${CONFIG}"
date -Is
sha256sum "${OUTPUT}"/*.json "${OUTPUT}"/*.jsonl
