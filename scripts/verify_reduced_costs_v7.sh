#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Compile OptiSolve C++ application ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
  -o solver/optisolve

printf '\n== Run C++ solver tests ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/solver_tests.cpp solver/simplex.cpp \
  -o /tmp/optisolve_solver_tests_v7
/tmp/optisolve_solver_tests_v7

printf '\n== Verify JSON exports entering-variable coefficients ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/trace_json_export_test.cpp solver/simplex.cpp solver/json_export.cpp \
  -o /tmp/optisolve_trace_json_test_v7
/tmp/optisolve_trace_json_test_v7
python -m json.tool /tmp/optisolve_ratio_trace.json >/dev/null
python - <<'PY'
import json
with open('/tmp/optisolve_ratio_trace.json', encoding='utf-8') as handle:
    result = json.load(handle)
pivot = next(step for step in result['trace'] if step['event'] == 'pivot')
costs = pivot['reduced_costs']
assert costs, 'reduced_costs missing from pivot trace'
by_name = {item['variable']: item for item in costs}
assert by_name['x1']['selected'] is True
assert by_name['x1']['eligible'] is True
assert by_name['x1']['tableau_coefficient'] == -4
assert by_name['x2']['eligible'] is True
assert by_name['x2']['selected'] is False
assert pivot['ratio_tests'][1]['ratio'] == 2
print('JSON trace contains objective-row coefficients and the selected entering variable.')
PY

printf '\n== Check Python syntax ==\n'
python -m py_compile api/main.py visualizer/algorithm_trace_animation.py tests/test_api.py

printf '\n== Check frontend JavaScript syntax ==\n'
python - <<'PY'
from pathlib import Path
source = Path('frontend/index.html').read_text(encoding='utf-8')
start = source.find('<script>')
end = source.find('</script>', start + len('<script>'))
if start < 0 or end < 0:
    raise SystemExit('Could not find inline frontend script.')
Path('/tmp/optisolve_frontend_v7.js').write_text(
    source[start + len('<script>'):end], encoding='utf-8'
)
PY
if command -v node >/dev/null 2>&1; then
  node --check /tmp/optisolve_frontend_v7.js
else
  echo 'Node.js is not installed; skipped JavaScript syntax check.'
fi

printf '\n== Run FastAPI tests ==\n'
python -m pytest -v tests/test_api.py

printf '\nAll OptiSolve reduced-cost and redundant-bound checks passed.\n'
