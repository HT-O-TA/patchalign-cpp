#!/bin/bash
set -euo pipefail
REPO=/mingli01/project/ht/patchalign-cpp
PREFLIGHT=${1:?usage: submit_a3_formal.sh PRELIGHT_REPORT}
cd "${REPO}"
test -z "$(git status --porcelain)"
test -f "${PREFLIGHT}"
python -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["status"] == "passed"' "${PREFLIGHT}"
test -f /mingli01/data/patchalign-cpp/a3/formal-sft-v1/formal-data-lock.json
test ! -e "${REPO}/artifacts/a3/formal/m0-inference"
test ! -e "${REPO}/artifacts/a3/formal/sft-training"
test ! -e "${REPO}/artifacts/a3/formal/sft-inference"
m0=$(sbatch --parsable --export=ALL,FORMAL_ROLE=m0 slurm/a3_3_infer.sbatch)
m0_score=$(sbatch --parsable --dependency=afterok:${m0} --export=ALL,FORMAL_ROLE=m0 slurm/a3_3_score.sbatch)
train=$(sbatch --parsable --dependency=afterok:${m0} slurm/a3_3_train.sbatch)
sft=$(sbatch --parsable --dependency=afterok:${train} --export=ALL,FORMAL_ROLE=sft slurm/a3_3_infer.sbatch)
sft_score=$(sbatch --parsable --dependency=afterok:${sft} --export=ALL,FORMAL_ROLE=sft slurm/a3_3_score.sbatch)
compare=$(sbatch --parsable --dependency=afterok:${m0_score}:${sft_score} slurm/a3_3_compare.sbatch)
printf 'm0_inference=%s\nm0_score=%s\nsft_train=%s\nsft_inference=%s\nsft_score=%s\ncompare=%s\n' \
  "${m0}" "${m0_score}" "${train}" "${sft}" "${sft_score}" "${compare}"
