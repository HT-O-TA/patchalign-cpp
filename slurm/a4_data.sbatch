#!/bin/bash
#SBATCH --job-name=patchalign-a4-data
#SBATCH --partition=gre
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=24:00:00
#SBATCH --output=/mingli01/project/ht/patchalign-cpp/artifacts/a4/logs/a4-data-%j.out

set -euo pipefail
trap 'rc=$?; echo "A4 data failed: line=${LINENO} exit=${rc} command=${BASH_COMMAND}" >&2; exit ${rc}' ERR
ENV_PREFIX=/mingli01/project/ht/.conda_envs/patchalign-cpp
REPO=/mingli01/project/ht/patchalign-cpp
CONFIG=${REPO}/configs/data/a4_executable_preference_v1.json
MODEL=/mingli01/models/Qwen2.5-Coder-7B
BWRAP=/mingli01/project/ht/.tools/bubblewrap/0.12.0/install/bin/bwrap
READINESS=${REPO}/artifacts/a3/pre-a4-readiness-v1.json
export PATH="${ENV_PREFIX}/bin:${PATH}" PYTHONPATH="${REPO}/src:${REPO}" PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
hash -r
test "$(command -v python)" = "${ENV_PREFIX}/bin/python"
test "$(python -c 'import sys; print(sys.prefix)')" = "${ENV_PREFIX}"
test -x "${BWRAP}"
test -z "$(cd "${REPO}" && git status --porcelain)"
test -f "${READINESS}"
mkdir -p "${REPO}/artifacts/a4/logs" /mingli01/data/patchalign-cpp/a4
cd "${REPO}"
python -m pytest -q
python - <<'PY'
import json
from pathlib import Path
p=Path('/mingli01/project/ht/patchalign-cpp/artifacts/a3/pre-a4-readiness-v1.json')
r=json.loads(p.read_text())
assert r['a4_ready'] is False and r['a4_started'] is False
assert 'supplementary_confirmation_passed' in r['blockers']
PY
if ! test -f /mingli01/data/patchalign-cpp/a4/executable-candidates-v1/candidate-manifest.json; then
  test ! -e /mingli01/data/patchalign-cpp/a4/executable-candidates-v1
  python -u scripts/preference/build_a4_executable_candidates.py --config "${CONFIG}"
fi
if ! test -f /mingli01/data/patchalign-cpp/a4/executable-source-v1/preference-source-manifest.json; then
  test ! -e /mingli01/data/patchalign-cpp/a4/executable-source-v1
  python -u scripts/preference/qualify_a4_executable_candidates.py --config "${CONFIG}" --bwrap "${BWRAP}" --model-path "${MODEL}"
fi
python -u scripts/preference/finalize_a4_generation_config.py \
  --data-config "${CONFIG}" --model-path "${MODEL}" \
  --environment-lock "${ENV_PREFIX}/repro/pip-freeze.txt"
sha256sum "${REPO}/artifacts/a4/generation-config-v1.json" "${REPO}/artifacts/a4/prompts-v1.jsonl"
