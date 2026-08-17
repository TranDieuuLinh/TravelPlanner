#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 PROMPT_FILE [OUTPUT_FILE]" >&2
  exit 2
fi

prompt_file="$1"
output_file="${2:-agy-output.json}"
[[ -f "$prompt_file" ]] || { echo "prompt file not found: $prompt_file" >&2; exit 2; }
command -v agy >/dev/null || { echo "agy is not installed or not on PATH" >&2; exit 127; }

# agy 1.1.x supports print mode and JSON output. Keep the worker in the current
# working tree; this script intentionally does not perform any Git operation.
agy --print --output-format json --print-timeout 30m "$(<"$prompt_file")" | tee "$output_file"
