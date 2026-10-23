#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Compile C++ solver ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
  -o solver/optisolve

printf '\n== Run C++ solver tests ==\n'
g++ -std=c++17 -Wall -Wextra -pedantic \
  tests/solver_tests.cpp solver/simplex.cpp \
  -o /tmp/optisolve_solver_tests
/tmp/optisolve_solver_tests

printf '\n== Check Python syntax ==\n'
python -m py_compile api/main.py visualizer/algorithm_trace_animation.py tests/test_api.py

printf '\n== Run API tests ==\n'
python -m pytest -v tests/test_api.py

printf '\nAll Trace Animation v0.5 checks completed successfully.\n'
