#!/bin/bash
#SBATCH --job-name=patchalign-a34-confirm-compare
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-confirm-compare-%j.out

set -euo pipefail
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
export PATH="${ENV_PREFIX}/bin:${PATH}"
export PYTHONPATH="${REPO}/src:${REPO}"
export PYTHONNOUSERSITE=1
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -m pytest -q
python -u scripts/training/compare_a3_confirmation.py --config configs/evaluation/a3_confirmation_comparison_v1.json
sha256sum artifacts/a3/confirmation/comparison-v1.json
