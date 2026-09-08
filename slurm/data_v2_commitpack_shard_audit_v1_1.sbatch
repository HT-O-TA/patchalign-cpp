#!/bin/bash
#SBATCH --job-name=patchalign-dv2-cp-audit11
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/commitpack-shard-audit-v1-1-%j.out

set -euo pipefail
trap 'rc=$?; echo "CommitPack shard audit v1.1 failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_commitpack_shard_audit_v1_1.json
SHARD=/mingli01/data/patchalign-cpp/data-v2/commitpack/5eee2c845bf88dbffcafedb6e80d2a72a43fe575/data/c++/c++-0001.jsonl
OUTPUT=${REPO}/artifacts/data-v2/commitpack-shard-audit-v1-1
EXPECTED_BYTES=523946192
EXPECTED_SHA=dfdd55f56f7be3bf4b8d2ccad8ea39910b4dd2c18ee296f5a991d134e57f367f

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
test "$(stat -c %s "${SHARD}")" -eq "${EXPECTED_BYTES}"
test "$(sha256sum "${SHARD}" | cut -d ' ' -f 1)" = "${EXPECTED_SHA}"

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs
printf 'stage=data_v2_commitpack_shard_audit_v1_1 job_id=%s host=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python scripts/data/audit_data_v2_commitpack_shard.py --config "${CONFIG}" --preflight-only
python -u scripts/data/audit_data_v2_commitpack_shard.py --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/candidate-audit.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"
