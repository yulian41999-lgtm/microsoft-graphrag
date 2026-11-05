#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
if [ -r logs/embedding.pid ]; then
  existing_pid="$(cat logs/embedding.pid)"
  if kill -0 "$existing_pid" 2>/dev/null && [ -r "/proc/$existing_pid/cmdline" ] && tr '\0' ' ' < "/proc/$existing_pid/cmdline" | grep -q 'scripts/embedding_server.py'; then
    echo "BGE-M3 is already starting/running, PID=$existing_pid"; exit 0
  fi
fi
exec 9>logs/embedding-start.lock
flock -n 9 || { echo "BGE-M3 startup/service lock is already held"; exit 0; }
export HF_HOME="$PWD/.cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2
if curl -fsS --max-time 3 http://127.0.0.1:18086/health >/dev/null 2>&1; then
  echo 'BGE-M3 is already available on localhost:18086'; exit 0
fi
nohup .venv-bge/bin/python -u scripts/embedding_server.py >> logs/embedding.log 2>&1 < /dev/null &
echo "$!" > logs/embedding.pid
printf 'BGE-M3 starting, PID=%s\n' "$!"
