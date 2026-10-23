#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Compile C++ application ==\n'
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
  -o solver/optisolve

printf '\n== C++ solver regression tests ==\n'
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  tests/solver_tests.cpp solver/simplex.cpp -o /tmp/optisolve_release_v14_solver_tests
/tmp/optisolve_release_v14_solver_tests

printf '\n== Algorithm walkthrough and row-operation tests ==\n'
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  tests/trace_walkthrough_test.cpp solver/simplex.cpp \
  -o /tmp/optisolve_release_v14_trace_tests
/tmp/optisolve_release_v14_trace_tests

g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  tests/trace_json_export_test.cpp solver/simplex.cpp solver/json_export.cpp \
  -o /tmp/optisolve_release_v14_json_trace_tests
/tmp/optisolve_release_v14_json_trace_tests
python -m json.tool /tmp/optisolve_ratio_trace.json >/dev/null

printf '\n== Python/API/parser/geometry tests ==\n'
python -m py_compile \
  api/main.py api/natural_language.py \
  visualizer/lpp_animation.py visualizer/lpp_geometry.py \
  visualizer/algorithm_trace_animation.py \
  tests/test_api.py tests/test_natural_language.py tests/test_lpp_geometry.py \
  scripts/e2e_smoke_v14.py
python -m pytest -q tests/test_api.py tests/test_natural_language.py tests/test_lpp_geometry.py

printf '\n== Frontend JavaScript syntax and release markers ==\n'
python - <<'PY'
from pathlib import Path
html = Path('frontend/index.html').read_text(encoding='utf-8')
start = html.find('<script>')
end = html.find('</script>', start + len('<script>'))
assert start >= 0 and end > start, 'Inline frontend script not found.'
Path('/tmp/optisolve_release_v14_frontend.js').write_text(
    html[start + len('<script>'):end], encoding='utf-8'
)
for marker in ('Describe it in words', 'Parse into model', 'controls playsinline'):
    assert marker in html, f'Missing required UI marker: {marker}'
print('Frontend release markers passed.')
PY
if command -v node >/dev/null 2>&1; then
  node --check /tmp/optisolve_release_v14_frontend.js
else
  echo 'WARNING: Node.js unavailable; frontend JS parser check skipped.'
fi

if [[ "${1:-}" == "--extended" ]]; then
  printf '\n== Extended randomized method-consistency sweep ==\n'
  g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
    tests/randomized_solver_consistency.cpp solver/simplex.cpp \
    -o /tmp/optisolve_release_v14_randomized
  /tmp/optisolve_release_v14_randomized
fi

printf '\nPASS: Release automated checks finished.\n'
printf 'Next required target-machine checks:\n'
printf '  bash scripts/smoke_test_manim_v12.sh\n'
printf '  # Start Uvicorn in another terminal, then:\n'
printf '  python scripts/e2e_smoke_v14.py\n'
