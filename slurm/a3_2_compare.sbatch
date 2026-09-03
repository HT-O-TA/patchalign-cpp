#!/bin/bash
#SBATCH --job-name=patchalign-a32-compare
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a32-compare-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.2 compare failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
BF16_TRAIN=${BF16_TRAIN_JOB_ID:?missing BF16_TRAIN_JOB_ID}
NF4_TRAIN=${NF4_TRAIN_JOB_ID:?missing NF4_TRAIN_JOB_ID}
BF16_SCORE=${BF16_SCORE_JOB_ID:?missing BF16_SCORE_JOB_ID}
NF4_SCORE=${NF4_SCORE_JOB_ID:?missing NF4_SCORE_JOB_ID}
BF16_DIR=${REPO}/artifacts/a3/sft-pilot/bf16_lora/${BF16_TRAIN}
NF4_DIR=${REPO}/artifacts/a3/sft-pilot/nf4_qlora/${NF4_TRAIN}
M0_SCORE=${REPO}/artifacts/a3/baseline/m0_base/93717/scoring-v2/93822
OUTPUT=${REPO}/artifacts/a3/comparison-a32/${SLURM_JOB_ID}/comparison.json
GATES=${REPO}/configs/evaluation/quality_gates_v1.json

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -z "$(cd "${REPO}" && git status --porcelain)"

echo "stage=A3.2_sft_pilot_compare"
echo "job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is

cd "${REPO}"
python -u scripts/training/compare_a3_sft_pilot.py \
  --bf16-run-dir "${BF16_DIR}" \
  --bf16-score-dir "${BF16_DIR}/inference/scoring-v2/${BF16_SCORE}" \
  --nf4-run-dir "${NF4_DIR}" \
  --nf4-score-dir "${NF4_DIR}/inference/scoring-v2/${NF4_SCORE}" \
  --m0-score-dir "${M0_SCORE}" \
  --quality-gates "${GATES}" \
  --output "${OUTPUT}"

date -Is
sha256sum "${OUTPUT}"
