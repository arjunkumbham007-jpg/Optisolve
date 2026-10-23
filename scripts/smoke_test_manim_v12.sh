#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/manim" ]]; then
  MANIM="$ROOT/.venv/bin/manim"
elif command -v manim >/dev/null 2>&1; then
  MANIM="$(command -v manim)"
else
  echo "ERROR: Manim not found. Activate .venv or install Manim into it." >&2
  exit 1
fi

for tool in latex dvisvgm ffmpeg ffprobe; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: Required video-render dependency '$tool' is missing." >&2
    echo "Check /video-health in OptiSolve after starting the server." >&2
    exit 1
  fi
done

printf '\n== Manim environment ==\n'
"$MANIM" --version
latex --version | sed -n '1p'
dvisvgm --version | sed -n '1p'
ffmpeg -version | sed -n '1p'

printf '\n== Compile solver ==\n'
g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
  -o solver/optisolve

render_case() {
  local label="$1"
  local stdin_payload="$2"
  local method="$3"
  printf '\n== Solve fixture: %s (%s) ==\n' "$label" "$method"
  (cd "$ROOT/solver" && printf '%b' "$stdin_payload" | ./optisolve --algorithm "$method" > /tmp/optisolve_video_smoke_solver.log)
  python - <<'PY'
import json
from pathlib import Path
p=Path('solver/optisolve_result.json')
obj=json.loads(p.read_text(encoding='utf-8'))
assert obj.get('status') == 'optimal', f"Solver status: {obj.get('status')}: {obj.get('message')}"
assert isinstance(obj.get('trace'), list) and obj['trace'], 'Solver did not export a trace.'
assert obj.get('solution'), 'Solver did not export a solution.'
print('Solver JSON:', obj['status'], 'objective=', obj['solution']['objective_value'], 'trace events=', len(obj['trace']))
PY

  printf '\n== Render the actual tableau-trace MP4 ==\n'
  rm -f media/videos/algorithm_trace_animation/480p15/AlgorithmTraceAnimation.mp4
  "$MANIM" -ql "$ROOT/visualizer/algorithm_trace_animation.py" AlgorithmTraceAnimation
  local trace_mp4="$ROOT/media/videos/algorithm_trace_animation/480p15/AlgorithmTraceAnimation.mp4"
  if [[ ! -s "$trace_mp4" ]]; then
    echo "ERROR: Manim returned without a non-empty trace MP4: $trace_mp4" >&2
    exit 1
  fi
  ls -lh "$trace_mp4"
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$trace_mp4"

  if [[ "$(python -c 'import json;print(len(json.load(open("solver/optisolve_result.json"))["model"]["objective_coefficients"]))')" == "2" ]]; then
    printf '\n== Render the actual graphical-explanation MP4 ==\n'
    rm -f media/videos/lpp_animation/480p15/LPPAnimation.mp4
    "$MANIM" -ql "$ROOT/visualizer/lpp_animation.py" LPPAnimation
    local graph_mp4="$ROOT/media/videos/lpp_animation/480p15/LPPAnimation.mp4"
    if [[ ! -s "$graph_mp4" ]]; then
      echo "ERROR: Manim returned without a non-empty graph MP4: $graph_mp4" >&2
      exit 1
    fi
    ls -lh "$graph_mp4"
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$graph_mp4"
  fi
}

# Mixed-constraint LP. This exercises two-phase trace output plus graph drawing
# of <= and >= boundaries in the same model.
MIXED=$'max\n2\n3\n3 2\n1 1 <= 4\n1 0 >= 1\n0 1 >= 1\n'
render_case "mixed-constraint graph" "$MIXED" "two-phase"

if [[ "${1:-}" == "--equality" ]]; then
  # Optional second real render for a line-shaped equality-feasible set.
  EQUALITY=$'max\n2\n3\n1 1\n1 1 = 4\n1 0 <= 3\n0 1 <= 3\n'
  render_case "equality feasible segment" "$EQUALITY" "two-phase"
fi

printf '\nSUCCESS: Manim generated non-empty MP4 files for the requested fixture(s).\n'
echo "The solver JSON and test videos now contain the final fixture used by this script. A new website solve replaces them."
