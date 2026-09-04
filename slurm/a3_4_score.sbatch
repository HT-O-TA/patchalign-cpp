#!/bin/bash
#SBATCH --job-name=patchalign-a34-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=12:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-score-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 scoring failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
BINDING=${REPO}/configs/evaluation/a3_sft_r2_scoring_v1.json
SCORING_CONFIG=${REPO}/configs/evaluation/a3_scoring_v2.json
INFERENCE=${REPO}/artifacts/a3/sft-r2/inference
SCORE=${INFERENCE}/scoring-v2
HOLDOUT=/mingli01/data/patchalign-cpp/a3/formal-holdout-v1
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
PREFLIGHT=${REPO}/artifacts/a3/sft-r2/scoring-preflight-${SLURM_JOB_ID}.json
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -x "${BWRAP}"
test -f "${INFERENCE}/run-manifest.json"
test ! -e "${SCORE}"
test -z "$(cd "${REPO}" && git status --porcelain)"
mkdir -p "${REPO}/artifacts/a3/sft-r2" "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_sft_r2_score job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/training/check_a3_sft_r2_scoring.py \
  --config "${BINDING}" --bwrap "${BWRAP}" --report "${PREFLIGHT}"
python -u scripts/baseline/score_a3_baseline.py \
  --holdout-dir "${HOLDOUT}" \
  --predictions "${INFERENCE}/predictions.jsonl" \
  --inference-manifest "${INFERENCE}/run-manifest.json" \
  --bwrap "${BWRAP}" \
  --scoring-config "${SCORING_CONFIG}" \
  --output-dir "${SCORE}"
date -Is
sha256sum "${PREFLIGHT}" "${SCORE}/scores.jsonl" "${SCORE}/score-summary.json" "${SCORE}/score-manifest.json"
