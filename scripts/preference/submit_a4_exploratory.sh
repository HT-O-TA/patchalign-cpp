#!/bin/bash
set -euo pipefail
REPO=/mingli01/project/ht/patchalign-cpp
READINESS=${REPO}/artifacts/a3/pre-a4-readiness-v1.json
cd "${REPO}"
test -z "$(git status --porcelain)"
test -f "${READINESS}"
python - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('/mingli01/project/ht/patchalign-cpp/artifacts/a3/pre-a4-readiness-v1.json').read_text())
assert r['a4_ready'] is False and r['a4_started'] is False
assert 'supplementary_confirmation_passed' in r['blockers']
PY
bash -n slurm/a4_data.sbatch
bash -n slurm/a4_generate.sbatch
DATA_JOB=$(sbatch --parsable slurm/a4_data.sbatch)
GPU_JOB=$(sbatch --parsable --dependency="afterok:${DATA_JOB}" slurm/a4_generate.sbatch)
printf 'a4_data_job_id=%s\na4_gpu_job_id=%s\na4_mode=owner_authorized_exploratory\n' "${DATA_JOB}" "${GPU_JOB}"
