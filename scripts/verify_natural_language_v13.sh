#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Verify existing OptiSolve solver, trace, API, geometry, and video pipeline ==\n'
bash scripts/verify_video_pipeline_v12.sh

printf '\n== Verify natural-language parser and endpoint ==\n'
python -m py_compile api/main.py api/natural_language.py tests/test_natural_language.py
python -m pytest -q tests/test_natural_language.py

printf '\n== Verify full FastAPI regression suite ==\n'
python -m pytest -q tests/test_api.py tests/test_natural_language.py

echo 'All OptiSolve natural-language v1.3 checks passed.'
