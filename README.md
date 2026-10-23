# OptiSolve v1.5 — Public Beta Preparation

OptiSolve is an educational linear-programming solver and algorithm visualizer. It combines a C++ optimization engine, FastAPI, a browser frontend, and Manim-generated videos.

## Features

- Standard Simplex, Two-Phase Simplex, and Big-M.
- Up to 20 decision variables and 100 constraints in the web interface.
- Maximize/minimize and method-dependent support for `<=`, `>=`, and `=`.
- Trace-backed tableaus, reduced-cost choices, minimum-ratio tests, pivot operations, and phase transitions.
- For two-variable problems, a graphical explanation; for supported traces, a separate Manim algorithm video.
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

## Deploy publicly with Docker + Caddy

This project needs an environment capable of running C++ and rendering Manim/FFmpeg/LaTeX videos. The included VPS deployment is the recommended first public beta path.

1. Provision a Linux VPS, install Docker Engine and the Docker Compose plugin, and point your domain's DNS A record to the server.
2. Allow inbound TCP 80 and 443 (UDP 443 is optional).
3. `cp .env.example .env` and replace `DOMAIN` and `OPTISOLVE_BASE_URL` with a domain you actually own.
4. Run `docker compose config`, then `docker compose up --build -d`.
5. Follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and run the live end-to-end smoke test before sharing the URL.
6. Follow [docs/GOOGLE_INDEXING.md](docs/GOOGLE_INDEXING.md) to submit the sitemap in Google Search Console.

A real domain, DNS changes, a running public host, and Search Console verification require actions in accounts controlled by the owner. No domain is purchased or website deployed by this source package.

## Known limitations

- This is a constrained public beta, not a high-traffic production SaaS. Solves are synchronous, one render is admitted at a time per app process, and a basic process-local rate limiter is used. Do not add multiple Uvicorn workers/replicas until admission/rate limiting is moved to shared infrastructure and rendering is moved to a durable job queue.
- Generated job results and MP4s expire and can be removed by the cleanup cap; job-specific video links are temporary.
- Public users who have a generated video's UUID-based URL can view it until cleanup. Do not submit sensitive or confidential LP models.
- The natural-language parser handles explicit formula-style math wording; it is not a general business-story understanding system.
- Graphs are two-dimensional. Higher-dimensional models get numerical results and algorithm-trace output.
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
