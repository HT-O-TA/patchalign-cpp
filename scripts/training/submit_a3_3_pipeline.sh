#!/bin/bash
set -euo pipefail

REPO=/mingli01/project/ht/patchalign-cpp
CANDIDATES=/mingli01/data/patchalign-cpp/a3/formal-holdout-candidates-v1
HOLDOUT=/mingli01/data/patchalign-cpp/a3/formal-holdout-v1
SFT=/mingli01/data/patchalign-cpp/a3/formal-sft-v1
BASE=${REPO}/artifacts/a3/formal

cd "${REPO}"
test -z "$(git status --porcelain)"
test -f "${CANDIDATES}/candidate-manifest.json"
test ! -e "${HOLDOUT}"
test ! -e "${SFT}"
test ! -e "${BASE}/m0-inference"
test ! -e "${BASE}/sft-training"
test ! -e "${BASE}/sft-inference"

qualify=$(sbatch --parsable slurm/a3_3_qualify.sbatch)
finalize=$(sbatch --parsable --dependency=afterok:${qualify} slurm/a3_3_finalize.sbatch)
m0=$(sbatch --parsable --dependency=afterok:${finalize} \
  --export=ALL,FORMAL_ROLE=m0 slurm/a3_3_infer.sbatch)
m0_score=$(sbatch --parsable --dependency=afterok:${m0} \
  --export=ALL,FORMAL_ROLE=m0 slurm/a3_3_score.sbatch)
train=$(sbatch --parsable --dependency=afterok:${m0} slurm/a3_3_train.sbatch)
sft=$(sbatch --parsable --dependency=afterok:${train} \
  --export=ALL,FORMAL_ROLE=sft slurm/a3_3_infer.sbatch)
sft_score=$(sbatch --parsable --dependency=afterok:${sft} \
  --export=ALL,FORMAL_ROLE=sft slurm/a3_3_score.sbatch)
compare=$(sbatch --parsable --dependency=afterok:${m0_score}:${sft_score} \
  slurm/a3_3_compare.sbatch)

printf 'qualification=%s\nfinalization=%s\npreflight=%s\n' \
  "${qualify}" "${finalize}" "${BASE}/preflight-${finalize}.json"
printf 'm0_inference=%s\nm0_score=%s\nsft_train=%s\n' \
  "${m0}" "${m0_score}" "${train}"
printf 'sft_inference=%s\nsft_score=%s\ncompare=%s\n' \
  "${sft}" "${sft_score}" "${compare}"
