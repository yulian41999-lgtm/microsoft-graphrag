#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
export UV_CACHE_DIR="$PWD/.cache/uv" HF_HOME="$PWD/.cache/huggingface" TMPDIR="$PWD/tmp"
export TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2 LITELLM_LOCAL_MODEL_COST_MAP=True
scope="${1:-smoke}"
case "$scope" in smoke) root="$PWD/smoke" ;; full) root="$PWD" ;; *) echo 'Usage: bash scripts/index.sh [smoke|full]' >&2; exit 2 ;; esac
exec 9>"$root/.index.lock"
flock -n 9 || { echo 'An index job is already running for this scope' >&2; exit 1; }
.venv/bin/python scripts/write_index_status.py "$root" running
trap 'result=$?; .venv/bin/python scripts/write_index_status.py "$root" "$result"' EXIT
.venv/bin/graphrag index --root "$root"
