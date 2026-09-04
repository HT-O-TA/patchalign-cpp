#!/bin/bash
#SBATCH --job-name=patchalign-a34-confirm-q11
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-confirm-q11-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 confirmation v1.1 qualification failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/data/a3_confirmation_qualification_v1_1.json
OUTPUT=/mingli01/data/patchalign-cpp/a3/confirmation-v1-1
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -x "${BWRAP}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test ! -e "${OUTPUT}"
mkdir -p "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_confirmation_qualification_v1.1 job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
python -u scripts/data/qualify_a3_confirmation.py \
  --config "${CONFIG}" --bwrap "${BWRAP}" \
  --workers "${SLURM_CPUS_PER_TASK}" --batch-size 16
date -Is
sha256sum "${OUTPUT}/confirmation-manifest.json" "${OUTPUT}/qualification-results.jsonl" "${OUTPUT}/qualification-report.json"
