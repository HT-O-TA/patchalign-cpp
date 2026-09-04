#!/bin/bash
#SBATCH --job-name=patchalign-d4c-infer
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-infer-%j.out

set -euo pipefail
trap 'rc=$?; echo "Defects4C inference failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_external_v1.json
ENV_LOCK=${ENV_PREFIX}/repro/pip-freeze.txt
ROLE=${DEFECTS4C_ROLE:?submit with DEFECTS4C_ROLE=m0 or m1_r2}
case "${ROLE}" in m0|m1_r2) ;; *) exit 64 ;; esac
OUTPUT=${REPO}/artifacts/a3/defects4c/inference-${ROLE}
PREFLIGHT=${DEFECTS4C_PREFLIGHT:?submit with DEFECTS4C_PREFLIGHT=/absolute/preflight.json}
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${PREFLIGHT}"
mkdir -p "${REPO}/artifacts/a3/defects4c" "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_defects4c_inference role=${ROLE} job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
/usr/bin/nvidia-smi
cd "${REPO}"
python -u scripts/external/run_defects4c_inference.py --config "${CONFIG}" --role "${ROLE}" --preflight "${PREFLIGHT}" --environment-lock "${ENV_LOCK}" --output-dir "${OUTPUT}" --segment-seconds 27600
date -Is
test -f "${OUTPUT}/run-manifest.json"
sha256sum "${OUTPUT}/predictions.jsonl" "${OUTPUT}/run-manifest.json" "${OUTPUT}/generation-summary.json"
