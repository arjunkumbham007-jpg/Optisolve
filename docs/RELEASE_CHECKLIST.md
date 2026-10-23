# OptiSolve Public-Beta Release Checklist

## Source and tests

- [ ] Run `bash scripts/verify_public_launch_v15.sh`.
- [ ] Check `git diff --check` and review all changed source files.
- [ ] Run `bash scripts/smoke_test_manim_v12.sh` and its equality option.
- [ ] Start Uvicorn and run `python scripts/e2e_smoke_v14.py http://127.0.0.1:8000`.
- [ ] Verify separate solves return distinct job IDs and job-specific video URLs.
- [ ] Confirm expired/missing job links return 404 and never serve a different job's MP4.

## Container and live host

- [ ] Choose/register a domain and configure its DNS A record.
- [ ] Create `.env` from `.env.example`, using the real domain and HTTPS origin.
- [ ] Run `docker compose config`.
- [ ] Build and start with `docker compose up --build -d` on the VPS.
- [ ] Confirm `docker compose ps`, `docker compose logs -f optisolve caddy`, and `/healthz`.
- [ ] Run the real end-to-end smoke test against the HTTPS domain.
- [ ] Check HTTPS redirects/certificate, video playback, job cleanup, and rate-limit behavior.

## Search indexing

- [ ] Verify `/robots.txt`, `/sitemap.xml`, `/about`, and `/privacy` on the public domain.
- [ ] Confirm `OPTISOLVE_BASE_URL` equals the final canonical HTTPS origin.
- [ ] Verify the domain in Google Search Console via the current DNS-based instructions.
- [ ] Submit `/sitemap.xml` and request homepage indexing.
- [ ] Remember that Google controls crawling/indexing and does not guarantee ranking or timeline.

## Go/no-go

Call it a **public beta** only after the actual container build and public end-to-end render test pass. The app is still not designed for high concurrent traffic; a durable render queue and shared rate limiter are needed before broader scale.
