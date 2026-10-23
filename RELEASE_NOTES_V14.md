# OptiSolve v1.4 Release Candidate Notes

## Included

- Release-focused README and operator documentation.
- Dependency inventory in `requirements.txt`.
- `.gitignore` for local environments, binaries, results, and generated media.
- Single-command automated verification script.
- Real browser/API/C++/Manim/MP4 end-to-end smoke test against a running local service.

## Release gate

Do not mark the MVP as complete until both of these have passed on the target Fedora machine:

1. `bash scripts/smoke_test_manim_v12.sh`
2. Start Uvicorn, then run `python scripts/e2e_smoke_v14.py`

The automated unit/API tests use mocks for rendering and therefore cannot substitute for these real render checks.
