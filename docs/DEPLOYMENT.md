# Public beta deployment (Docker + VPS)

OptiSolve uses a C++ solver, FastAPI, Manim, FFmpeg, and LaTeX. For the first public beta, deploy it as a Docker app on a small VPS where you control the system packages and can allow long-running rendering requests. A static-only hosting service is not sufficient for the complete app.

The v1.5 deployment prep adds request-scoped job folders, job-specific video URLs, a one-at-a-time solve guard, a basic per-client rate limit, automatic old-job cleanup, a non-root app container, Caddy HTTPS termination, and SEO routes. This is a **small public beta setup**, not an architecture for high traffic. For sustained traffic, replace synchronous rendering with a persistent job queue and separate worker processes.

## 1. Prerequisites

- A Linux VPS with enough CPU/RAM/disk for C++ solves and Manim/LaTeX rendering. Rendering time and memory grow with the problem and trace size.
- Docker Engine and the Docker Compose plugin installed.
- A registered domain that you control.
- DNS A record for the domain pointing at your VPS IPv4 address. Add an AAAA record only if the VPS really serves the app over IPv6.
- Firewall rules allowing inbound TCP 80 and 443. UDP 443 is optional and supports HTTP/3.

Do not publish the app on the public internet until `scripts/verify_public_launch_v15.sh` and the real end-to-end render test pass.

## 2. Configure the domain

Copy the environment template:

```bash
cp .env.example .env
nano .env
```

Replace the sample values with the exact public domain you own:

```dotenv
DOMAIN=your-real-domain.example
OPTISOLVE_BASE_URL=https://your-real-domain.example
OPTISOLVE_ENV=production
OPTISOLVE_JOB_TTL_HOURS=24
OPTISOLVE_MAX_STORED_JOBS=100
OPTISOLVE_SOLVE_LIMIT_PER_MINUTE=5
```

The `.example` suffix above is illustrative only; it will not issue a public TLS certificate. `DOMAIN` and `OPTISOLVE_BASE_URL` must refer to the actual domain.

## 3. Build and start

After DNS has been pointed to your VPS and ports 80/443 are reachable:

```bash
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs -f optisolve caddy
```

Caddy obtains and renews HTTPS certificates for the configured domain. The app container's port 8000 is only exposed to the Docker network, not published directly to the internet. The app runs one Uvicorn worker intentionally because the initial render semaphore and rate limiter are process-local.

## 4. Verify the live site

Replace the URL with your domain:

```bash
curl -fsS https://your-real-domain.example/healthz
curl -fsS https://your-real-domain.example/robots.txt
curl -fsS https://your-real-domain.example/sitemap.xml
curl -fsSI https://your-real-domain.example/
```

Then run the real end-to-end test from a machine with Python and ffprobe:

```bash
python scripts/e2e_smoke_v14.py https://your-real-domain.example
```

It performs a solve and fetches both actual MP4 endpoints, so it uses compute and may take several minutes. Do not run it repeatedly against the public site.

## 5. Operational behavior and limits

- Every solve gets a unique, unguessable job ID, separate result JSON, and separate graph/trace videos. This prevents simultaneous requests from overwriting or accidentally serving another request's output.
- The API allows only one active solve/render at a time per process; additional simultaneous requests receive HTTP 429 rather than competing for CPU/RAM.
- A small in-memory per-IP rate limit is applied. With a single worker it is coherent for a small beta. Use an edge/WAF rate limit if traffic grows.
- Jobs expire according to `OPTISOLVE_JOB_TTL_HOURS`, and the number of retained jobs is bounded by `OPTISOLVE_MAX_STORED_JOBS`. Video URLs intentionally stop working after cleanup.
- The rate limiter is in memory and resets on restart. This is not sufficient as the sole abuse-prevention control for a high-traffic production service.
- Do not scale to multiple Uvicorn workers or multiple app replicas without replacing process-local admission controls with shared coordination and a real job queue.
- Keep OS/Docker patches current, monitor disk usage, and check `docker compose logs` after failures.
- The formula parser expects explicit formula-like English, not arbitrary business narratives. Users must review the extracted model.
- Big-M can be numerically sensitive. Two-Phase is preferable for general reliability checks.

## Rollback

Keep the previous release archive/tag. For a code rollback, restore the corresponding Git revision or re-extract the known-good release, then run `docker compose up --build -d`. Runtime job data lives in a named Docker volume and is managed separately from the source release.
