#!/bin/bash
#SBATCH --job-name=patchalign-a34-confirm-score
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=12:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-confirm-score-%j.out

set -euo pipefail
trap 'rc=$?; echo "A3.4 scoring failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
SCORING_CONFIG=${REPO}/configs/evaluation/a3_scoring_v2.json
ROLE=${CONFIRMATION_ROLE:?submit with CONFIRMATION_ROLE=m0 or m1_r2}
case "${ROLE}" in m0|m1_r2) ;; *) exit 64 ;; esac
INFERENCE=${REPO}/artifacts/a3/confirmation/${ROLE}
SCORE=${INFERENCE}/scoring-v2
HOLDOUT=/mingli01/data/patchalign-cpp/a3/confirmation-v1-1
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
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
mkdir -p "${REPO}/artifacts/a3/confirmation" "${REPO}/artifacts/a3/logs"
echo "stage=A3.4_confirmation_score role=${ROLE} job_id=${SLURM_JOB_ID} host=$(hostname)"
date -Is
cd "${REPO}"
python -m pytest -q
python -u scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
python -u scripts/baseline/score_a3_baseline.py \
  --holdout-dir "${HOLDOUT}" \
  --predictions "${INFERENCE}/predictions.jsonl" \
  --inference-manifest "${INFERENCE}/run-manifest.json" \
  --bwrap "${BWRAP}" \
  --scoring-config "${SCORING_CONFIG}" \
  --output-dir "${SCORE}" \
  --manifest-name confirmation-manifest.json
date -Is
sha256sum "${SCORE}/scores.jsonl" "${SCORE}/score-summary.json" "${SCORE}/score-manifest.json"
