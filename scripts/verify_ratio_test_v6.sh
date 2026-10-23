#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Compile application ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
  -o solver/optisolve

printf '\n== Run C++ solver tests ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/solver_tests.cpp solver/simplex.cpp \
  -o /tmp/optisolve_solver_tests
/tmp/optisolve_solver_tests

printf '\n== Test ratio-test JSON export ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/trace_json_export_test.cpp solver/simplex.cpp solver/json_export.cpp \
  -o /tmp/optisolve_trace_json_test
/tmp/optisolve_trace_json_test
python -m json.tool /tmp/optisolve_ratio_trace.json >/dev/null
python - <<'PY'
import json
with open('/tmp/optisolve_ratio_trace.json', encoding='utf-8') as handle:
    result = json.load(handle)
pivot = next(step for step in result['trace'] if step['event'] == 'pivot')
assert len(pivot['ratio_tests']) == 3
assert pivot['ratio_tests'][1]['ratio'] == 2
assert pivot['ratio_tests'][1]['basic_variable'] == pivot['leaving_variable']
assert pivot['ratio_tests'][2]['eligible'] is False
print('Ratio-test JSON is valid and identifies the selected minimum row.')
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
    raise SystemExit('Could not find inline script in frontend/index.html')
Path('/tmp/optisolve_frontend_v6.js').write_text(
    source[start + len('<script>'):end], encoding='utf-8'
)
PY
if command -v node >/dev/null 2>&1; then
  node --check /tmp/optisolve_frontend_v6.js
else
  echo 'Node.js not installed; skipped JavaScript syntax check.'
fi

printf '\n== Run API tests ==\n'
python -m pytest -v tests/test_api.py

printf '\nAll OptiSolve trace ratio-test v0.6 checks completed successfully.\n'
