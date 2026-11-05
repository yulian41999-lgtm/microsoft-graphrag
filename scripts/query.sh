#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export LITELLM_LOCAL_MODEL_COST_MAP=True HF_HOME="$PWD/.cache/huggingface" TMPDIR="$PWD/tmp"
scope="${1:?Usage: query.sh smoke|full local|global|basic question}"; method="${2:?Missing method}"; question="${3:?Missing question}"
case "$scope" in smoke) root="$PWD/smoke" ;; full) root="$PWD" ;; *) exit 2 ;; esac
.venv/bin/graphrag query --root "$root" --method "$method" --community-level 0 --response-type "简洁中文回答，先直接回答，再列依据；使用CommonMark段落或列表，不使用表格" "$question"
