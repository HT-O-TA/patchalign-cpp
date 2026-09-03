#!/bin/bash
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --output=slurm-%j.out

set -euo pipefail
trap 'rc=$?; echo "A2b command failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR

ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
CANDIDATES=/mingli01/data/patchalign-cpp/a2/candidates-v3
HOLDOUT=/mingli01/data/patchalign-cpp/a2/holdout-v3
RESULT=/mingli01/data/patchalign-cpp/a2/execution-results-v3.jsonl
SUMMARY=/mingli01/data/patchalign-cpp/a2/execution-summary-v3.json

export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONNOUSERSITE=1
hash -r

echo "stage=A2b_qualification_and_execution"
echo "host=$(hostname)"
echo "job_id=${SLURM_JOB_ID:-unknown}"
echo "repo=${REPO}"
echo "bwrap=${BWRAP}"
echo "candidates=${CANDIDATES}"
echo "holdout=${HOLDOUT}"

test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -d "${REPO}/.git"
test -x "${BWRAP}"
test -f "${CANDIDATES}/candidate-manifest.json"
test -f "${CANDIDATES}/sha256sums.txt"
test ! -e "${HOLDOUT}"
test ! -e "${RESULT}"
test ! -e "${SUMMARY}"
echo "python=$(command -v python)"
echo "python_prefix=$(python -c 'import sys; print(sys.prefix)')"
echo "bwrap_version=$(${BWRAP} --version)"

(
  cd "${CANDIDATES}"
  sha256sum --quiet --check sha256sums.txt
)

cd "${REPO}"
test -z "$(git status --porcelain)"
python -m py_compile scripts/data/a2_output_matcher.py
python -m py_compile scripts/data/a2_sandbox_runtime.py
python -m py_compile scripts/data/check_a2_sandbox.py
python -m py_compile scripts/data/qualify_a2_holdout.py
python -m py_compile scripts/data/run_a2_cases.py
python -m py_compile scripts/data/check_a2_replay_stability.py
python -m py_compile scripts/data/summarize_a2_results.py
python scripts/data/check_a2_sandbox.py --bwrap "${BWRAP}"
python scripts/data/qualify_a2_holdout.py \
  --bwrap "${BWRAP}" \
  --candidate-dir "${CANDIDATES}" \
  --holdout-dir "${HOLDOUT}"

(
  cd "${HOLDOUT}"
  {
    sha256sum a2-manifest.json qualification-report.json qualification-results.jsonl
    find cases -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
  } > sha256sums.txt
  sha256sum --quiet --check sha256sums.txt
)

python scripts/data/run_a2_cases.py \
  --bwrap "${BWRAP}" \
  --holdout-dir "${HOLDOUT}" \
  --output "${RESULT}"
python scripts/data/check_a2_replay_stability.py \
  --qualification "${HOLDOUT}/qualification-results.jsonl" \
  --final "${RESULT}"
python scripts/data/summarize_a2_results.py \
  --input "${RESULT}" \
  --output "${SUMMARY}"

echo "git_commit=$(git rev-parse HEAD)"
echo "manifest_sha256=$(sha256sum "${HOLDOUT}/a2-manifest.json" | cut -d' ' -f1)"
echo "qualification_report_sha256=$(sha256sum "${HOLDOUT}/qualification-report.json" | cut -d' ' -f1)"
echo "qualification_results_sha256=$(sha256sum "${HOLDOUT}/qualification-results.jsonl" | cut -d' ' -f1)"
echo "holdout_sha256s_sha256=$(sha256sum "${HOLDOUT}/sha256sums.txt" | cut -d' ' -f1)"
echo "result_sha256=$(sha256sum "${RESULT}" | cut -d' ' -f1)"
echo "summary_sha256=$(sha256sum "${SUMMARY}" | cut -d' ' -f1)"
