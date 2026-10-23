#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Full solver / trace / API / geometry regressions ==\n'
bash scripts/verify_visualizer_v11.sh

printf '\n== Video pipeline static checks ==\n'
python -m py_compile api/main.py visualizer/lpp_animation.py visualizer/lpp_geometry.py visualizer/algorithm_trace_animation.py tests/test_api.py tests/test_lpp_geometry.py
python - <<'PY'
from pathlib import Path
import re
html = Path('frontend/index.html').read_text(encoding='utf-8')
script_start = html.find('<script>')
script_end = html.find('</script>', script_start + 8)
assert script_start >= 0 and script_end > script_start, 'Inline frontend JS not found.'
Path('/tmp/optisolve_video_v12_frontend.js').write_text(html[script_start + 8:script_end], encoding='utf-8')
assert 'video-diagnostics' in html
assert '/video-health' in html
assert 'controls playsinline' in html
print('Frontend contains video diagnostics and controlled HTML video players.')
PY
if command -v node >/dev/null 2>&1; then
  node --check /tmp/optisolve_video_v12_frontend.js
  echo 'Frontend JavaScript syntax passed.'
else
  echo 'Node.js unavailable; skipped JavaScript syntax validation.'
fi

printf '\n== Verify video smoke test is installed ==\n'
test -x scripts/smoke_test_manim_v12.sh
echo 'Real Manim MP4 smoke test is available: bash scripts/smoke_test_manim_v12.sh'
echo 'Optional equality-region render: bash scripts/smoke_test_manim_v12.sh --equality'
echo 'All OptiSolve video-pipeline v1.2 automated checks passed.'
