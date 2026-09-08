#!/bin/bash
#SBATCH --job-name=patchalign-a5-dpo-pre
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-dpo-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 DPO preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/training/a5_dpo_v1_1.json
OUTPUT=${REPO}/artifacts/a5/dpo-preflight-v1.1/cpu-preflight.json

export PATH="${ENV_PREFIX}/bin:/usr/bin:/bin"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
mkdir -p "$(dirname "${OUTPUT}")" "${REPO}/artifacts/a5/logs"

printf 'stage=a5_dpo_preflight job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/training/check_a5_dpo.py --config "${CONFIG}" --output "${OUTPUT}"
sha256sum "${CONFIG}" "${OUTPUT}"
date -Is
