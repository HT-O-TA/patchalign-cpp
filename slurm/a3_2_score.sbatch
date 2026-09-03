#!/bin/bash
#SBATCH --job-name=patchalign-a32-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a32-score-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.2 score failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v3
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
SCORING_CONFIG=${REPO}/configs/evaluation/a3_scoring_v2.json
MODE=${PILOT_MODE:?missing PILOT_MODE}
SOURCE_JOB=${TRAIN_JOB_ID:?missing TRAIN_JOB_ID}
RUN_DIR=${REPO}/artifacts/a3/sft-pilot/${MODE}/${SOURCE_JOB}
INFERENCE_DIR=${RUN_DIR}/inference
SCORE_DIR=${INFERENCE_DIR}/scoring-v2/${SLURM_JOB_ID}

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r

test "${MODE}" = bf16_lora -o "${MODE}" = nf4_qlora
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -x "${BWRAP}"
test -f "${INFERENCE_DIR}/predictions.jsonl"
test -z "$(cd "${REPO}" && git status --porcelain)"

echo "stage=A3.2_sft_pilot_score"
echo "mode=${MODE}"
echo "train_job_id=${SOURCE_JOB}"
echo "score_job_id=${SLURM_JOB_ID}"
echo "host=$(hostname)"
date -Is

cd "${REPO}"
python -u scripts/baseline/score_a3_baseline.py \
  --holdout-dir "${HOLDOUT}" \
  --predictions "${INFERENCE_DIR}/predictions.jsonl" \
  --inference-manifest "${INFERENCE_DIR}/run-manifest.json" \
  --bwrap "${BWRAP}" \
  --scoring-config "${SCORING_CONFIG}" \
  --output-dir "${SCORE_DIR}"

date -Is
sha256sum "${SCORE_DIR}/scores.jsonl" \
  "${SCORE_DIR}/score-summary.json" "${SCORE_DIR}/score-manifest.json"
