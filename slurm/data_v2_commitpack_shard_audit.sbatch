#!/bin/bash
#SBATCH --job-name=patchalign-dv2-cp-audit
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=04:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/commitpack-shard-audit-%j.out

set -euo pipefail
trap 'rc=$?; echo "CommitPack shard audit failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_commitpack_shard_audit_v1.json
REVISION=5eee2c845bf88dbffcafedb6e80d2a72a43fe575
DATA_DIR=/mingli01/data/patchalign-cpp/data-v2/commitpack/${REVISION}/data/c++
SHARD=${DATA_DIR}/c++-0001.jsonl
PART=${SHARD}.part
URL='https://huggingface.co/datasets/bigcode/commitpack/resolve/5eee2c845bf88dbffcafedb6e80d2a72a43fe575/data/c%2B%2B/c%2B%2B-0001.jsonl?download=true'
EXPECTED_BYTES=523946192
EXPECTED_SHA=dfdd55f56f7be3bf4b8d2ccad8ea39910b4dd2c18ee296f5a991d134e57f367f
OUTPUT=${REPO}/artifacts/data-v2/commitpack-shard-audit-v1

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
AVAILABLE_KB="$(df --output=avail /mingli01/data/patchalign-cpp | tail -1)"
test "${AVAILABLE_KB}" -ge 5242880

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs "${DATA_DIR}"
printf 'stage=data_v2_commitpack_shard_audit job_id=%s host=%s available_kb=%s\n' \
  "${SLURM_JOB_ID}" "$(hostname)" "${AVAILABLE_KB}"
date -Is
python -m pytest -q
python scripts/data/audit_data_v2_commitpack_shard.py --config "${CONFIG}" --preflight-only

if test -f "${SHARD}"; then
  test "$(stat -c %s "${SHARD}")" -eq "${EXPECTED_BYTES}"
  test "$(sha256sum "${SHARD}" | cut -d ' ' -f 1)" = "${EXPECTED_SHA}"
else
  curl --fail --location --retry 5 --retry-delay 10 --continue-at - \
    --output "${PART}" "${URL}"
  test "$(stat -c %s "${PART}")" -eq "${EXPECTED_BYTES}"
  test "$(sha256sum "${PART}" | cut -d ' ' -f 1)" = "${EXPECTED_SHA}"
  mv "${PART}" "${SHARD}"
fi

python -u scripts/data/audit_data_v2_commitpack_shard.py --config "${CONFIG}"
date -Is
sha256sum \
  "${OUTPUT}/candidate-audit.jsonl" \
  "${OUTPUT}/summary.json" \
  "${OUTPUT}/run-manifest.json"
