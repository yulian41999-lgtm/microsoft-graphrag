#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export LITELLM_LOCAL_MODEL_COST_MAP=True HF_HOME="$PWD/.cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR="$PWD/tmp"
# Wait for the explicitly started dependency installation; signal 0 only checks existence.
while kill -0 2962870 2>/dev/null; do sleep 10; done
.venv-embedding/bin/python -c 'import torch, sentence_transformers; assert torch.cuda.is_available(); print("Embedding dependencies ready:",torch.__version__)'
bash scripts/start_embedding.sh
for attempt in $(seq 1 120); do
  if curl -fsS --max-time 3 http://127.0.0.1:18086/health > logs/embedding-health.json 2>/dev/null; then break; fi
  sleep 5
done
curl -fsS --max-time 3 http://127.0.0.1:18086/health
