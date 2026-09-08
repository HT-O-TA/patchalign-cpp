#!/bin/bash
#SBATCH --job-name=patchalign-dv2-beetle-meta11
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=artifacts/data-v2/logs/beetlebox-metadata-audit-v1-1-%j.out

set -euo pipefail
trap 'rc=$?; echo "BeetleBox metadata audit failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/data/data_v2_beetlebox_metadata_audit_v1_1.json
REVISION=ac12f9cd8afac9095498ff69cafe45ce8747b4ef
DATA_DIR=/mingli01/data/patchalign-cpp/data-v2/beetlebox/${REVISION}/data
TRAIN=${DATA_DIR}/train-00000-of-00001.parquet
TEST=${DATA_DIR}/test-00000-of-00001.parquet
OUTPUT=${REPO}/artifacts/data-v2/beetlebox-metadata-audit-v1-1

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
python -c 'import pyarrow; print(pyarrow.__version__)'

cd "${REPO}"
export PATCHALIGN_GIT_COMMIT="$(git rev-parse HEAD)"
mkdir -p artifacts/data-v2/logs "${DATA_DIR}"
printf 'stage=data_v2_beetlebox_metadata_audit job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
python -m pytest -q
python scripts/data/audit_data_v2_beetlebox_metadata.py --config "${CONFIG}" --preflight-only

download_and_verify() {
  target=$1
  expected_bytes=$2
  expected_sha=$3
  url=$4
  part=${target}.part
  if test -f "${target}"; then
    test "$(stat -c %s "${target}")" -eq "${expected_bytes}"
    test "$(sha256sum "${target}" | cut -d ' ' -f 1)" = "${expected_sha}"
    return
  fi
  curl --fail --location --retry 5 --retry-delay 10 --continue-at - --output "${part}" "${url}"
  test "$(stat -c %s "${part}")" -eq "${expected_bytes}"
  test "$(sha256sum "${part}" | cut -d ' ' -f 1)" = "${expected_sha}"
  mv "${part}" "${target}"
}

download_and_verify "${TRAIN}" 9775583 976a51ba2203cf7df84f1b3c046e395feb6a4c7612b30aba292b691939ebdc09 \
  'https://huggingface.co/datasets/bug-localization/BeetleBox/resolve/ac12f9cd8afac9095498ff69cafe45ce8747b4ef/data/train-00000-of-00001.parquet?download=true'
download_and_verify "${TEST}" 9599672 a0b257e772df19cd0ccdd46a02c202d83a5295b3febf74992550e118c4d8b9d2 \
  'https://huggingface.co/datasets/bug-localization/BeetleBox/resolve/ac12f9cd8afac9095498ff69cafe45ce8747b4ef/data/test-00000-of-00001.parquet?download=true'

python -u scripts/data/audit_data_v2_beetlebox_metadata.py --config "${CONFIG}"
date -Is
sha256sum "${OUTPUT}/summary.json" "${OUTPUT}/run-manifest.json"
