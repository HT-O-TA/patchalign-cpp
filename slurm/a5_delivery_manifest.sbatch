#!/bin/bash
#SBATCH --job-name=patchalign-a5-delivery
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-delivery-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 delivery manifest failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_final_v1.json
OUTPUT=${REPO}/artifacts/a5/delivery-manifest-v1.json
export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${REPO}/artifacts/a5/final-evaluation-v1/comparison.json"
test ! -e "${OUTPUT}"
printf 'stage=a5_delivery_manifest job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/evaluation/build_a5_delivery_manifest.py --config "${CONFIG}" --output "${OUTPUT}"
sha256sum "${OUTPUT}"
date -Is
