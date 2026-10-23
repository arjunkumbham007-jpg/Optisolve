#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Run the complete v0.9 regression suite, now including the Phase I cleanup case.
bash scripts/verify_next_iteration_v9.sh

# Add a deterministic randomized consistency sweep across solver methods.
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  tests/randomized_solver_consistency.cpp solver/simplex.cpp \
  -o /tmp/optisolve_randomized_solver_consistency_v10
/tmp/optisolve_randomized_solver_consistency_v10

echo "All OptiSolve solver-correctness v1.0 checks passed."
