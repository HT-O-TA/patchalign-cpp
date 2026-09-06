#!/bin/bash
#SBATCH --job-name=patchalign-data-v2-audit
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu16
#SBATCH --output=artifacts/data-v2/logs/supply-audit-%j.out

set -euo pipefail
trap 'echo "Data-v2 supply audit failed" >&2' ERR
umask 077

REPO=/mingli01/project/ht/patchalign-cpp
ENV=/mingli01/project/ht/.conda_envs/patchalign-cpp
export PATH="$ENV/bin:$PATH"
export PYTHONPATH="$REPO/src:$REPO"
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=4
hash -r

test "$(command -v python)" = "$ENV/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "$ENV"
test -z "$(cd "$REPO" && git status --porcelain --untracked-files=no)"

cd "$REPO"
mkdir -p artifacts/data-v2/logs
echo "stage=data_v2_supply_audit"
echo "job_id=$SLURM_JOB_ID"
echo "host=$(hostname)"
date -Is

python -m pytest -q tests/unit/test_data_v2_supply_audit.py
python -u scripts/data/audit_data_v2_supply.py   --config configs/data/data_v2_supply_audit_v1.json

sha256sum   artifacts/data-v2/supply-audit-v1/candidate-audit.jsonl   artifacts/data-v2/supply-audit-v1/summary.json   artifacts/data-v2/supply-audit-v1/run-manifest.json
date -Is
