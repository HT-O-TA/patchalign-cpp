#!/bin/bash
#SBATCH --job-name=patchalign-dv2-bugscpp-license
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/bugscpp-project-license-probe-%j.out

set -euo pipefail
trap 'rc=$?; echo "BugsCpp project/license probe failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_bugscpp_project_license_probe_v1.json
REVISION=be5cc489cb2b3127ec3b73cb4adfdd290807f55b
SOURCE=/mingli01/data/patchalign-cpp/data-v2/bugscpp/${REVISION}/repo
INCOMING=${SOURCE}.incoming
OUTPUT=${REPO}/artifacts/data-v2/bugscpp-project-license-probe-v1

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs "$(dirname "${SOURCE}")"
printf 'stage=data_v2_bugscpp_project_license_probe job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python scripts/data/audit_data_v2_bugscpp_projects.py --config "${CONFIG}" --preflight-only

if test ! -d "${SOURCE}/.git"; then
  test ! -e "${INCOMING}"
  git clone --filter=blob:none --no-checkout \
    'https://github.com/Suresoft-GLaDOS/bugscpp.git' "${INCOMING}"
  if ! git -C "${INCOMING}" cat-file -e "${REVISION}^{commit}"; then
    git -C "${INCOMING}" fetch --filter=blob:none --depth=1 origin "${REVISION}"
  fi
  test "$(git -C "${INCOMING}" rev-parse "${REVISION}^{commit}")" = "${REVISION}"
  mv "${INCOMING}" "${SOURCE}"
fi

test "$(git -C "${SOURCE}" rev-parse "${REVISION}^{commit}")" = "${REVISION}"
python -u scripts/data/audit_data_v2_bugscpp_projects.py --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/project-decisions.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"
