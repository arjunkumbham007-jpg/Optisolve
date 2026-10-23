# Architecture Overview

```text
Browser (HTML/CSS/JavaScript)
       | /parse-problem, /solve
       v
FastAPI backend + single-render admission guard
       | request-scoped UUID workspace
       +--> C++ LP engine -> job-specific JSON + recorded trace
       +--> Manim graph scene (2 variables only)
       +--> Manim algorithm-trace scene
       v
Job-scoped MP4 endpoints -> browser video players
```

## Main directories

- `solver/`: LP model, Standard Simplex/Two-Phase/Big-M, trace generation, JSON export.
- `api/`: FastAPI endpoints, model validation, formula-style natural-language parser, per-job output routing and SEO endpoints.
- `frontend/`: single-page UI plus About and Privacy pages.
- `visualizer/`: graphical LP scene, geometry helpers, algorithm trace scene.
- `tests/`: C++ regressions, randomized consistency, API/parser/geometry tests.
- `scripts/`: verification, real-render smoke test, and end-to-end test.
- `runtime/jobs/<job-id>/`: temporary per-solve JSON and MP4 outputs, cleaned by job TTL/storage cap.

## Public-beta containment

The web service uses per-request workspaces so concurrent output files do not overwrite each other. Rendering is synchronous and guarded by one process-local slot; start exactly one Uvicorn worker. A small process-local rate limiter is included. For significant traffic, move solve/render work to a persistent queue with bounded workers and shared rate limiting/coordination.
