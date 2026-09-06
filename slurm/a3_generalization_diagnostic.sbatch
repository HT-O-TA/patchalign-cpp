#!/bin/bash
#SBATCH --job-name=patchalign-a3-generalization
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --exclude=gpu16
#SBATCH --output=artifacts/a3/logs/a3-generalization-%j.out

set -euo pipefail
umask 077
export PYTHONNOUSERSITE=1

REPO=/mingli01/project/ht/patchalign-cpp
ENV=/mingli01/project/ht/.conda_envs/patchalign-cpp
cd "$REPO"
mkdir -p artifacts/a3/logs

test -x "$ENV/bin/python"
test -z "$(git status --porcelain)"

"$ENV/bin/python" -m pytest -q
"$ENV/bin/python" scripts/diagnostics/analyze_generalization_failure.py \
  --repo-root "$REPO" \
  --config configs/evaluation/a3_generalization_diagnostic_v1.json

sha256sum \
  artifacts/a3/diagnostics/generalization-v1/summary.json \
  artifacts/a3/diagnostics/generalization-v1/case-audit.jsonl \
  artifacts/a3/diagnostics/generalization-v1/run-manifest.json
