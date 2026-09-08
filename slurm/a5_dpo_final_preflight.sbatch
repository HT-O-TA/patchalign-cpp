#!/bin/bash
#SBATCH --job-name=patchalign-a5-final-pre
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-final-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 final preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
CONFIG=${REPO}/configs/evaluation/a5_dpo_final_v1.json
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
mkdir -p "${REPO}/artifacts/a5/logs"
printf 'stage=a5_dpo_final_preflight job_id=%s host=%s\n' "${SLURM_JOB_ID}" "$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/evaluation/check_a5_dpo_final.py --config "${CONFIG}"
sha256sum "${CONFIG}" "${REPO}/artifacts/a5/final-evaluation-v1/preflight.json"
date -Is
