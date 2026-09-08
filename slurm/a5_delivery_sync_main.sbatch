#!/bin/bash
#SBATCH --job-name=patchalign-a5-sync-main
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --exclude=gpu12,gpu16
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a5/logs/a5-sync-main-%j.out

set -euo pipefail
trap 'rc=$?; echo "A5 delivery sync failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
REPO=/mingli01/project/ht/patchalign-cpp
RECOVERY_BRANCH=a5-eval-recovery-97614
RECOVERY_COMMIT=fbe0717be11ca55648cd4d9d69c22c0fa707471c
: "${PATCHALIGN_DELIVERY_COMMIT:?PATCHALIGN_DELIVERY_COMMIT must be exported by sbatch}"

cd "${REPO}"
test "$(git branch --show-current)" = "${RECOVERY_BRANCH}"
test "$(git rev-parse HEAD)" = "${RECOVERY_COMMIT}"
test -z "$(git status --porcelain)"
test -f artifacts/a5/final-evaluation-v1/comparison.json
test -f artifacts/a5/final-evaluation-v1/failure-analysis.json
git cat-file -e "${PATCHALIGN_DELIVERY_COMMIT}^{commit}"

printf 'stage=a5_delivery_sync job_id=%s from=%s target=%s\n' "${SLURM_JOB_ID}" "${RECOVERY_COMMIT}" "${PATCHALIGN_DELIVERY_COMMIT}"
date -Is
git switch main
git merge --ff-only "${PATCHALIGN_DELIVERY_COMMIT}"
test "$(git rev-parse HEAD)" = "${PATCHALIGN_DELIVERY_COMMIT}"
test -z "$(git status --porcelain)"
git status --short --branch
date -Is
