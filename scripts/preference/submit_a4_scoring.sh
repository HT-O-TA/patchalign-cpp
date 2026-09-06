#!/bin/bash
set -euo pipefail
REPO=/mingli01/project/ht/patchalign-cpp
cd "${REPO}"
test -z "$(git status --porcelain)"
bash -n slurm/a4_score_preflight.sbatch
bash -n slurm/a4_score_array.sbatch
bash -n slurm/a4_preference_finalize.sbatch
PREFLIGHT_JOB=$(sbatch --parsable slurm/a4_score_preflight.sbatch)
SCORE_JOB=$(sbatch --parsable --dependency="afterok:${PREFLIGHT_JOB}" slurm/a4_score_array.sbatch)
FINALIZE_JOB=$(sbatch --parsable --dependency="afterok:${SCORE_JOB}" slurm/a4_preference_finalize.sbatch)
printf 'a4_score_preflight_job_id=%s\na4_score_array_job_id=%s\na4_finalize_job_id=%s\na4_mode=owner_authorized_exploratory\n' "${PREFLIGHT_JOB}" "${SCORE_JOB}" "${FINALIZE_JOB}"
