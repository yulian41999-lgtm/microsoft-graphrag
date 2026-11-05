#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export LITELLM_LOCAL_MODEL_COST_MAP=True UV_CACHE_DIR="$PWD/.cache/uv" HF_HOME="$PWD/.cache/huggingface" TMPDIR="$PWD/tmp"
copy_pid="$(cat logs/copy-bge-environment.pid)"
while kill -0 "$copy_pid" 2>/dev/null; do sleep 5; done
.venv-bge/bin/python - <<'PY'
import torch,sentence_transformers,transformers,sys
from pathlib import Path
for m in [torch,sentence_transformers,transformers]:assert Path(m.__file__).is_relative_to(Path(sys.prefix))
assert torch.cuda.is_available()
print('Independent BGE environment verified',sys.version,torch.__version__,flush=True)
PY
bash scripts/start_embedding.sh
for attempt in $(seq 1 60); do
 if curl -fsS --max-time 3 http://127.0.0.1:18086/health > logs/embedding-health.json 2>/dev/null; then break; fi
 sleep 5
done
curl -fsS --max-time 3 http://127.0.0.1:18086/health
uv pip freeze --python .venv-bge/bin/python > requirements-embedding.lock.txt
.venv/bin/graphrag index --root smoke --dry-run > logs/dry-run-final.log 2>&1
bash scripts/index.sh smoke > logs/smoke-index-final.log 2>&1
.venv/bin/python scripts/verify_outputs.py smoke > logs/verify-smoke.log 2>&1
bash scripts/query.sh smoke local '烟金罚决字〔2024〕34号处罚的机构是什么，罚款多少？请根据资料回答并引用来源。' > smoke/local-answer.md 2> logs/query-local.log
bash scripts/query.sh smoke global '这些文档体现了哪些银行监管主题？请用三条中文要点回答，并引用资料。' > smoke/global-answer.md 2> logs/query-global.log
printf 'SMOKE_VALIDATION_AND_QUERIES_COMPLETE\n'
