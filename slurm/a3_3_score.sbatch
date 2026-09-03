#!/bin/bash
#SBATCH --job-name=patchalign-a33-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a33-score-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.3 score failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
ROLE=${FORMAL_ROLE:?submit with FORMAL_ROLE=m0-or-sft}
INFERENCE=${REPO}/artifacts/a3/formal/${ROLE}-inference
SCORE=${INFERENCE}/scoring-v2
HOLDOUT=/mingli01/data/patchalign-cpp/a3/formal-holdout-v1
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
hash -r
test "${ROLE}" = m0 -o "${ROLE}" = sft
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test -x "${BWRAP}"
test -f "${INFERENCE}/run-manifest.json"
test ! -e "${SCORE}"
test -z "$(cd "${REPO}" && git status --porcelain)"
echo "stage=A3.3_formal_score role=${ROLE} job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -u scripts/baseline/score_a3_baseline.py \
  --holdout-dir "${HOLDOUT}" --predictions "${INFERENCE}/predictions.jsonl" \
  --inference-manifest "${INFERENCE}/run-manifest.json" --bwrap "${BWRAP}" \
  --scoring-config configs/evaluation/a3_scoring_v2.json --output-dir "${SCORE}"
date -Is
sha256sum "${SCORE}/scores.jsonl" "${SCORE}/score-summary.json" "${SCORE}/score-manifest.json"
