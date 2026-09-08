#!/bin/bash
#SBATCH --job-name=patchalign-a5-pref-audit
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:20:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/a5/logs/a5-pref-audit-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 preference audit failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/a5_resume_dpo_preference_v1.json
OUTPUT=${REPO}/artifacts/a5/dpo-preference-v1

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"

cd "${REPO}"
mkdir -p artifacts/a5/logs
printf 'stage=a5_preference_audit job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python -u scripts/preference/audit_resume_dpo_preferences.py --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/preferences.jsonl" \
  "${OUTPUT}/audit.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"
