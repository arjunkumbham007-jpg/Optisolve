# OptiSolve — Interactive Linear Programming Solver & Visualizer

OptiSolve is an educational linear-programming solver and algorithm visualizer. It combines a C++ optimization engine, FastAPI, a browser frontend, and Manim-generated videos.

## Screenshots

<p align="center">
  <img src="docs/screenshots/01-homepage.png" alt="OptiSolve interface" width="49%" />
  <img src="docs/screenshots/02-solution.png" alt="Optimization results" width="49%" />
</p>

<p align="center">
  <img src="docs/screenshots/03-visualization.png" alt="Optimization visualization" width="49%" />
  <img src="docs/screenshots/04-algorithm-trace.png" alt="Algorithm trace visualization" width="49%" />
</p>

## Features

- Standard Simplex, Two-Phase Simplex, and Big-M.
- Up to 20 decision variables and 100 constraints in the web interface.
- Maximize/minimize and method-dependent support for `<=`, `>=`, and `=`.
- Trace-backed tableaus, reduced-cost choices, minimum-ratio tests, pivot operations, and phase transitions.
- Dimension-aware visual explanations: 2D graphs for two variables, 3D feasible-region views for three, and variable/contribution profiles plus constraint diagnostics for four or more variables.
- Conservative formula-style natural-language parsing. Extracted models are editable and must be reviewed before solving.
- Per-solve workspaces and unique video URLs so outputs from separate jobs are not accidentally overwritten or cross-served.
- Basic solve admission/rate limits, job cleanup, crawler metadata, `robots.txt`, sitemap, About/Privacy pages, and Docker+Caddy deployment files.

## Run locally (Fedora)

Install system dependencies used by Manim and LaTeX, then:

```bash
cd ~/projects/optisolve
source .venv/bin/activate
python -m pip install -r requirements.txt

g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
  solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
  -o solver/optisolve

uvicorn api.main:app --reload
```

Open <http://127.0.0.1:8000/>. Local API docs are at `/docs` while `OPTISOLVE_ENV` is not `production`. Renderer prerequisites are reported at `/video-health`.

## Run the checks

```bash
source .venv/bin/activate
bash scripts/verify_public_launch_v15.sh
```

Then, with Uvicorn running in a separate terminal, perform a real C++ solve and Manim renders:

```bash
python scripts/e2e_smoke_v14.py http://127.0.0.1:8000
```

Mocked API tests do not substitute for this real-render test.

## Run and demonstrate locally

OptiSolve currently runs locally; a public hosted instance has not been deployed.

Start the Docker services:

    docker compose up -d --build

Check the API:

    curl -fsS http://localhost/healthz

Run a real end-to-end test, including C++ solving and Manim video rendering:

    ./.venv/bin/python scripts/e2e_smoke_v14.py http://localhost

Open `http://localhost` in your browser to demonstrate the application.
Run the automated tests with:

    ./.venv/bin/python -m pytest -q tests/

The end-to-end test complements the automated tests by performing real
video rendering and checking MP4 delivery.

## Known limitations

- This is a constrained public beta, not a high-traffic production SaaS. Solves are synchronous, one render is admitted at a time per app process, and a basic process-local rate limiter is used. Do not add multiple Uvicorn workers/replicas until admission/rate limiting is moved to shared infrastructure and rendering is moved to a durable job queue.
- Generated job results and MP4s expire and can be removed by the cleanup cap; job-specific video links are temporary.
- Public users who have a generated video's UUID-based URL can view it until cleanup. Do not submit sensitive or confidential LP models.
- The natural-language parser handles explicit formula-style math wording; it is not a general business-story understanding system.
- Two-variable models receive 2D graph explanations, three-variable models receive 3D feasible-region views, and models with four or more variables receive variable/contribution profiles and constraint diagnostics alongside numerical results and algorithm traces.
- Big-M may be numerically sensitive; compare with Two-Phase for difficult models.
- Public indexing is not guaranteed. A sitemap and Search Console request improve discovery but do not guarantee a search position.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Public deployment](docs/DEPLOYMENT.md)
- [Google indexing](docs/GOOGLE_INDEXING.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Solver correctness notes](README_SOLVER_CORRECTNESS_V10.md)
- [Graph visualizer notes](README_VISUALIZER_V11.md)
- [Natural-language parser notes](README_NATURAL_LANGUAGE_V13.md)

## Video rendering quality

OptiSolve renders Manim videos using the `OPTISOLVE_VIDEO_QUALITY` setting:

- `high` (default): 1920x1080 at 30 fps.
- `medium`: 1280x720 at 30 fps.
- `low`: 480p at 15 fps.

Set this variable in the project's `.env` file. Docker Compose forwards it to
the application container. Higher-quality renders use more CPU time and may
take longer, especially for large algorithm traces or high-dimensional models.
Existing videos are not upgraded automatically; rerender a problem to produce
a video at the newly selected quality.
