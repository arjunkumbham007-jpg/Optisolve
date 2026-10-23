#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Full solver/API/visualizer regressions + randomized consistency ==\n'
bash scripts/verify_release_v14.sh --extended

printf '\n== Public launch assets ==\n'
python - <<'PY'
from pathlib import Path
checks = {
    "Dockerfile": Path("Dockerfile"),
    "Compose file": Path("compose.yaml"),
    "Caddyfile": Path("Caddyfile"),
    "environment template": Path(".env.example"),
    "Google indexing guide": Path("docs/GOOGLE_INDEXING.md"),
    "public deployment guide": Path("docs/DEPLOYMENT.md"),
    "favicon": Path("favicon.svg"),
    "About page": Path("frontend/about.html"),
    "Privacy page": Path("frontend/privacy.html"),
}
for name, path in checks.items():
    assert path.is_file() and path.stat().st_size > 0, f"Missing {name}: {path}"
print(f"[PASS] {len(checks)} public-launch assets exist.")

compose = Path("compose.yaml").read_text(encoding="utf-8")
dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
assert "OPTISOLVE_BASE_URL" in compose and "DOMAIN" in compose
assert '"--workers", "1"' in dockerfile
assert "--media_dir" in Path("api/main.py").read_text(encoding="utf-8")
print("[PASS] Domain config, one-worker policy, and per-job render wiring are present.")

html = Path("frontend/index.html").read_text(encoding="utf-8")
assert 'name="description"' in html
assert "OPTISOLVE_STRUCTURED_DATA" in Path("api/main.py").read_text(encoding="utf-8")
assert "/jobs/" in Path("api/main.py").read_text(encoding="utf-8")
print("[PASS] SEO metadata hooks and job-scoped artifact routes are present.")
PY

if command -v docker >/dev/null 2>&1 && [[ -f .env ]]; then
  docker compose config --quiet
  printf '[PASS] Docker Compose configuration parsed by Docker.\n'
else
  printf 'NOTE: Docker config/build was not verified here. Install Docker and set .env on the target host, then run docker compose config.\n'
fi

printf '\nPASS: public-launch verification finished.\n'
printf 'Before going public, still run a real Manim smoke test and an end-to-end solve/render test on the target host.\n'
