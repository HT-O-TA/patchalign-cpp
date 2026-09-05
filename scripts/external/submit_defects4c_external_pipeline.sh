#!/bin/bash
set -euo pipefail
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_external_v1.json
cd "${REPO}"
test -z "$(git status --porcelain)"
test -f "${CONFIG}"
test -f /mingli01/data/patchalign-cpp/external/defects4c/qualified-v1/manifest.json
bash -n slurm/a3_4_defects4c_inference_preflight.sbatch
bash -n slurm/a3_4_defects4c_inference.sbatch
bash -n slurm/a3_4_defects4c_score.sbatch
bash -n slurm/a3_4_defects4c_score_aggregate.sbatch
bash -n slurm/a3_4_finalize_pre_a4.sbatch
CASE_COUNT=$(python -c "import json; print(json.load(open('${CONFIG}'))['dataset']['case_count'])")
test "${CASE_COUNT}" -ge 150
test "${CASE_COUNT}" -le 203
LAST_INDEX=$((CASE_COUNT - 1))
PREFLIGHT_JOB=$(sbatch --parsable slurm/a3_4_defects4c_inference_preflight.sbatch)
PREFLIGHT_REPORT=${REPO}/artifacts/a3/defects4c/inference-preflight-${PREFLIGHT_JOB}.json
M0_JOB=$(sbatch --parsable --dependency="afterok:${PREFLIGHT_JOB}" --export="ALL,DEFECTS4C_ROLE=m0,DEFECTS4C_PREFLIGHT=${PREFLIGHT_REPORT}" slurm/a3_4_defects4c_inference.sbatch)
M1_JOB=$(sbatch --parsable --dependency="afterok:${PREFLIGHT_JOB}" --export="ALL,DEFECTS4C_ROLE=m1_r2,DEFECTS4C_PREFLIGHT=${PREFLIGHT_REPORT}" slurm/a3_4_defects4c_inference.sbatch)
SCORE_JOB=$(sbatch --parsable --dependency="afterok:${M0_JOB}:${M1_JOB}" --array="0-${LAST_INDEX}%4" slurm/a3_4_defects4c_score.sbatch)
AGGREGATE_JOB=$(sbatch --parsable --dependency="afterok:${SCORE_JOB}" slurm/a3_4_defects4c_score_aggregate.sbatch)
READINESS_JOB=$(sbatch --parsable --dependency="afterok:${AGGREGATE_JOB}" slurm/a3_4_finalize_pre_a4.sbatch)
printf 'preflight_job_id=%s\nm0_gpu_job_id=%s\nm1_r2_gpu_job_id=%s\nscore_array_job_id=%s\naggregate_job_id=%s\nreadiness_job_id=%s\n' "${PREFLIGHT_JOB}" "${M0_JOB}" "${M1_JOB}" "${SCORE_JOB}" "${AGGREGATE_JOB}" "${READINESS_JOB}"
