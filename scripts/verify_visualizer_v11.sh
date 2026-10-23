#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Run solver, trace, API, and randomized correctness regressions ==\n'
bash scripts/verify_solver_correctness_v10.sh

printf '\n== Test mixed-constraint graphical geometry ==\n'
python -m pytest -v tests/test_lpp_geometry.py

printf '\n== Check visualizer and API Python syntax ==\n'
python -m py_compile api/main.py visualizer/lpp_animation.py visualizer/lpp_geometry.py tests/test_api.py tests/test_lpp_geometry.py

printf '\n== Check Manim scene imports / geometry availability ==\n'
python - <<'PY'
from pathlib import Path
scene = Path('visualizer/lpp_animation.py').read_text(encoding='utf-8')
geometry = Path('visualizer/lpp_geometry.py')
assert 'from lpp_geometry import' in scene
assert geometry.is_file()
print('Graph scene imports the local pure-Python geometry module.')
PY

printf '\nAll OptiSolve visualizer v1.1 automated checks passed.\n'
printf 'Note: this script does not render MP4 videos; run a live solve in Fedora to verify Manim rendering.\n'
