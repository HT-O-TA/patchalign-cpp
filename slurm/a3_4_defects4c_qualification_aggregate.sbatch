#!/bin/bash
#SBATCH --job-name=patchalign-d4c-aggregate
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a3/logs/a34-d4c-aggregate-%j.out

set -euo pipefail
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/external/a3_defects4c_qualification_v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
test -z "$(cd "${REPO}" && git status --porcelain)"
cd "${REPO}"
python -u scripts/external/aggregate_defects4c_qualification.py --config "${CONFIG}"
sha256sum /mingli01/data/patchalign-cpp/external/defects4c/qualified-v1/manifest.json /mingli01/data/patchalign-cpp/external/defects4c/qualified-v1/prompts.jsonl
