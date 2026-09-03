#!/bin/bash
#SBATCH --job-name=patchalign-a32-preflight
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a32-preflight-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.2 preflight failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
PILOT_CONFIG=${REPO}/configs/training/a3_sft_pilot_v1.json
BASELINE_CONFIG=${REPO}/configs/evaluation/a3_baseline_v1.json
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v3
M0_DIR=${REPO}/artifacts/a3/baseline/m0_base/93717
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

echo "stage=A3.2_sft_pilot_preflight"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is

cd "${REPO}"
python -m pytest -q
python scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
python scripts/baseline/check_a3_baseline.py \
  --config "${BASELINE_CONFIG}" \
  --holdout-dir "${HOLDOUT}" \
  --bwrap "${BWRAP}"
python scripts/training/check_a3_sft_pilot.py \
  --config "${PILOT_CONFIG}" \
  --m0-inference-dir "${M0_DIR}"

date -Is
sha256sum "${PILOT_CONFIG}" scripts/training/*.py slurm/a3_2_*.sbatch
