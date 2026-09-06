#!/bin/bash
#SBATCH --job-name=patchalign-dv2-sources
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --exclude=gpu16
#SBATCH --output=artifacts/data-v2/logs/source-admission-%j.out

set -euo pipefail
trap 'echo "Data-v2 source admission validation failed" >&2' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV=/mingli01/project/ht/.conda_envs/patchalign-cpp
export PATH="$ENV/bin:$PATH"
export PYTHONPATH="$REPO/src:$REPO"
export PYTHONNOUSERSITE=1
hash -r

test "$(command -v python)" = "$ENV/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "$ENV"
test -z "$(cd "$REPO" && git status --porcelain --untracked-files=no)"

cd "$REPO"
mkdir -p artifacts/data-v2/logs
echo "stage=data_v2_source_admission"
echo "job_id=$SLURM_JOB_ID"
echo "host=$(hostname)"
date -Is

python -m pytest -q tests/unit/test_data_v2_source_admission.py
python scripts/data/check_data_v2_source_admission.py
date -Is
