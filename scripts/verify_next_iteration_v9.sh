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
  -o /tmp/optisolve_solver_tests_v9
/tmp/optisolve_solver_tests_v9

printf '\n== Verify each pivot leads to the next recorded decision ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/trace_walkthrough_test.cpp solver/simplex.cpp \
  -o /tmp/optisolve_trace_walkthrough_test_v9
/tmp/optisolve_trace_walkthrough_test_v9

printf '\n== Verify JSON exports pivot row operations ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/trace_json_export_test.cpp solver/simplex.cpp solver/json_export.cpp \
  -o /tmp/optisolve_trace_json_test_v9
/tmp/optisolve_trace_json_test_v9
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
operations = pivot.get('row_operations') or []
assert operations, 'row_operations missing from pivot trace'
assert operations[0]['operation'] == 'divide', 'pivot row normalization should be first'
assert any(item['operation'] == 'subtract_multiple' for item in operations), 'elimination operations missing'

pivot_index = result['trace'].index(pivot)
assert pivot_index + 1 < len(result['trace']), 'after-pivot state missing'
next_step = result['trace'][pivot_index + 1]
assert pivot.get('tableau_recorded') and next_step.get('tableau_recorded'), 'before/after tableau not recorded'
assert pivot['phase'] == next_step['phase'], 'selected transition crosses phases; use a within-phase pivot'
reconstructed = [list(map(float, row)) for row in pivot['tableau']]
for operation in operations:
    target = operation['target_row'] - 1
    source = operation['source_row'] - 1
    factor = operation['factor']
    if operation['operation'] == 'divide':
        reconstructed[target] = [value / factor for value in reconstructed[target]]
    elif operation['operation'] == 'subtract_multiple':
        reconstructed[target] = [value - factor * base for value, base in zip(reconstructed[target], reconstructed[source])]
    else:
        raise AssertionError(f"unknown row operation {operation['operation']}")
for actual_row, expected_row in zip(reconstructed, next_step['tableau']):
    assert len(actual_row) == len(expected_row)
    for actual, expected in zip(actual_row, expected_row):
        assert abs(actual - expected) < 1e-6, f"row operations don't reconstruct tableau: {actual} != {expected}"
print('JSON trace includes entering decisions, ratio tests, and row operations that reconstruct the next tableau.')
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
Path('/tmp/optisolve_frontend_v9.js').write_text(
    source[start + len('<script>'):end], encoding='utf-8'
)
PY
if command -v node >/dev/null 2>&1; then
  node --check /tmp/optisolve_frontend_v9.js
else
  echo 'Node.js is not installed; skipped JavaScript syntax check.'
fi

printf '\n== Run FastAPI tests ==\n'
python -m pytest -v tests/test_api.py

printf '\nAll OptiSolve next-iteration walkthrough and regression checks passed.\n'
