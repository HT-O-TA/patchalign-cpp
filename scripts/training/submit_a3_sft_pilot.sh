#!/bin/bash
set -euo pipefail

REPO=/mingli01/project/ht/patchalign-cpp
cd "${REPO}"
test -z "$(git status --porcelain)"
mkdir -p artifacts/a3/logs

preflight=$(sbatch --parsable slurm/a3_2_preflight.sbatch)
bf16_train=$(sbatch --parsable \
  --dependency="afterok:${preflight}" \
  --export=ALL,PILOT_MODE=bf16_lora \
  slurm/a3_2_train.sbatch)
nf4_train=$(sbatch --parsable \
  --dependency="afterok:${preflight},afterany:${bf16_train}" \
  --export=ALL,PILOT_MODE=nf4_qlora \
  slurm/a3_2_train.sbatch)
bf16_score=$(sbatch --parsable \
  --dependency="afterok:${bf16_train}" \
  --export=ALL,PILOT_MODE=bf16_lora,TRAIN_JOB_ID="${bf16_train}" \
  slurm/a3_2_score.sbatch)
nf4_score=$(sbatch --parsable \
  --dependency="afterok:${nf4_train}" \
  --export=ALL,PILOT_MODE=nf4_qlora,TRAIN_JOB_ID="${nf4_train}" \
  slurm/a3_2_score.sbatch)
comparison=$(sbatch --parsable \
  --dependency="afterok:${bf16_score}:${nf4_score}" \
  --export=ALL,BF16_TRAIN_JOB_ID="${bf16_train}",NF4_TRAIN_JOB_ID="${nf4_train}",BF16_SCORE_JOB_ID="${bf16_score}",NF4_SCORE_JOB_ID="${nf4_score}" \
  slurm/a3_2_compare.sbatch)

printf 'preflight=%s\n' "${preflight}"
printf 'bf16_train=%s\n' "${bf16_train}"
printf 'bf16_score=%s\n' "${bf16_score}"
printf 'nf4_train=%s\n' "${nf4_train}"
printf 'nf4_score=%s\n' "${nf4_score}"
printf 'comparison=%s\n' "${comparison}"
