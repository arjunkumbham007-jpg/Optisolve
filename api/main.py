import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
import re
import html
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .natural_language import parse_natural_language_problem

ROOT = Path(__file__).resolve().parents[1]
SOLVER_DIR = ROOT / "solver"
BINARY = SOLVER_DIR / "optisolve"
# Kept as the default path for local CLI workflows; API requests use isolated jobs.
RESULT_FILE = SOLVER_DIR / "optisolve_result.json"
RUNTIME_DIR = Path(os.environ.get("OPTISOLVE_RUNTIME_DIR", ROOT / "runtime")).expanduser().resolve()
JOBS_DIR = RUNTIME_DIR / "jobs"
SITE_URL = os.environ.get("OPTISOLVE_BASE_URL", "").strip().rstrip("/")
JOB_TTL_SECONDS = max(3600, int(os.environ.get("OPTISOLVE_JOB_TTL_HOURS", "24")) * 3600)
MAX_STORED_JOBS = max(10, int(os.environ.get("OPTISOLVE_MAX_STORED_JOBS", "100")))
SOLVE_LIMIT_PER_MINUTE = max(1, int(os.environ.get("OPTISOLVE_SOLVE_LIMIT_PER_MINUTE", "5")))
SOLVE_SLOT = threading.Semaphore(1)
_RATE_LOCK = threading.Lock()
_RATE_HISTORY: dict[str, list[float]] = {}


def discover_manim() -> Path:
    """Prefer the project venv, then allow an explicit/system Manim install."""
    override = os.environ.get("OPTISOLVE_MANIM")
    if override:
        return Path(override).expanduser()
    local = ROOT / ".venv" / "bin" / "manim"
    if local.is_file():
        return local
    system_manim = shutil.which("manim")
    return Path(system_manim) if system_manim else local


MANIM = discover_manim()
ANIMATION = ROOT / "visualizer" / "lpp_animation.py"
TRACE_ANIMATION = ROOT / "visualizer" / "algorithm_trace_animation.py"
MAX_VARIABLES = 20
MAX_CONSTRAINTS = 100

PRODUCTION = os.environ.get("OPTISOLVE_ENV", "development").lower() == "production"
app = FastAPI(
    title="OptiSolve API",
    version="1.5.0",
    docs_url=None if PRODUCTION else "/docs",
    redoc_url=None if PRODUCTION else "/redoc",
    openapi_url=None if PRODUCTION else "/openapi.json",
)


class Constraint(BaseModel):
    coefficients: list[float] = Field(min_length=1, max_length=MAX_VARIABLES)
    relation: str
    rhs: float


class LPPRequest(BaseModel):
    sense: str = "max"
    method: str = "simplex"
    objective_coefficients: list[float] = Field(min_length=1, max_length=MAX_VARIABLES)
    constraints: list[Constraint] = Field(min_length=1, max_length=MAX_CONSTRAINTS)


class NaturalLanguageRequest(BaseModel):
    text: str = Field(min_length=8, max_length=10000)


def number(value: float) -> str:
    return format(float(value), ".15g")


def normalize_sense(value: str) -> str:
    value = value.lower().strip()
    if value in {"max", "maximize", "maximise"}:
        return "max"
    if value in {"min", "minimize", "minimise"}:
        return "min"
    raise HTTPException(400, "Objective direction must be max or min.")


def normalize_method(value: str) -> tuple[str, str]:
    value = value.lower().strip()
    if value == "simplex":
        return "simplex", "simplex"
    if value in {"two-phase", "two_phase", "two phase"}:
        return "two-phase", "two_phase"
    if value in {"big-m", "big_m", "big m"}:
        return "big-m", "big_m"
    raise HTTPException(400, "Method must be simplex, two-phase, or big-m.")


def is_explicit_nonnegativity_bound(constraint: Constraint) -> bool:
    """Recognize a redundant row equivalent to x_i >= 0.

    OptiSolve already models every decision variable as nonnegative. Such a row
    is a variable-domain bound, not a structural constraint, so it should not
    force Standard Simplex to reject an otherwise supported model.
    """
    if constraint.relation != ">=" or constraint.rhs != 0:
        return False
    nonzero = [value for value in constraint.coefficients if value != 0]
    return len(nonzero) == 1 and nonzero[0] > 0


def add_nonnegativity_notice(message: str, count: int) -> str:
    if count == 0:
        return message
    noun = "constraint" if count == 1 else "constraints"
    return (
        f"{message} Ignored {count} explicit non-negativity {noun} because "
        "x_i >= 0 is already built into OptiSolve's variable domain."
    )


def run_manim(
    scene_file: Path,
    scene_name: str,
    *,
    result_json: Path,
    media_dir: Path,
    timeout: int = 180,
):
    """Render one scene into a per-job media directory."""
    if not scene_file.is_file():
        return False, f"Manim scene file not found: {scene_file}"
    if not MANIM.is_file():
        return False, (
            f"Manim executable not found at {MANIM}. Activate the project's .venv "
            "and install Manim, or set OPTISOLVE_MANIM to its executable path."
        )
    media_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OPTISOLVE_RESULT_JSON"] = str(result_json.resolve())
    try:
        process = subprocess.run(
            [str(MANIM), "-ql", "--media_dir", str(media_dir.resolve()), str(scene_file), scene_name],
            text=True,
            capture_output=True,
            cwd=ROOT,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, (
            f"Rendering {scene_name} exceeded {timeout} seconds. Check CPU usage, "
            "LaTeX/FFmpeg dependencies, and tableau size."
        )
    except OSError as exc:
        return False, f"Could not launch Manim for {scene_name}: {exc}"

    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "No error detail returned.")[-1800:]
        return False, f"Rendering {scene_name} failed: {detail}"
    return True, ""


def job_video_path(job_dir: Path, scene_stem: str, scene_name: str) -> Path:
    return job_dir / "media" / "videos" / scene_stem / "480p15" / f"{scene_name}.mp4"


def cleanup_old_jobs() -> None:
    """Bound temporary disk use; job links expire after JOB_TTL_SECONDS."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    jobs = []
    for candidate in JOBS_DIR.iterdir():
        if not candidate.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", candidate.name):
            continue
        try:
            modified = candidate.stat().st_mtime
        except OSError:
            continue
        if now - modified > JOB_TTL_SECONDS:
            shutil.rmtree(candidate, ignore_errors=True)
        else:
            jobs.append((modified, candidate))
    jobs.sort()
    excess = max(0, len(jobs) - MAX_STORED_JOBS + 1)
    for _, candidate in jobs[:excess]:
        shutil.rmtree(candidate, ignore_errors=True)


def get_job_directory(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "Generated artifact not found or expired.")
    base = JOBS_DIR.resolve()
    candidate = (base / job_id).resolve()
    if candidate.parent != base or not candidate.is_dir():
        raise HTTPException(404, "Generated artifact not found or expired.")
    return candidate


def solve_guard(request: Request):
    """Single-render guard plus a basic per-client rate limit for public demos."""
    host = request.client.host if request.client else "unknown"
    now = time.time()
    with _RATE_LOCK:
        recent = [stamp for stamp in _RATE_HISTORY.get(host, []) if now - stamp < 60]
        if host != "testclient" and len(recent) >= SOLVE_LIMIT_PER_MINUTE:
            _RATE_HISTORY[host] = recent
            raise HTTPException(429, "Solve rate limit reached. Please wait a minute and try again.")
        if host != "testclient":
            recent.append(now)
            _RATE_HISTORY[host] = recent
        # Avoid unbounded rate-history growth if many unique IPs visit.
        if len(_RATE_HISTORY) > 2000:
            for key in list(_RATE_HISTORY)[:1000]:
                _RATE_HISTORY.pop(key, None)

    if not SOLVE_SLOT.acquire(blocking=False):
        raise HTTPException(429, "Another solve is being rendered right now. Please retry shortly.")
    try:
        yield
    finally:
        SOLVE_SLOT.release()


def site_absolute_url(path: str = "/") -> str:
    return f"{SITE_URL}{path}" if SITE_URL else ""


def nonempty_video(path: Path) -> bool:
    """Require a fresh, non-empty render before exposing an MP4 endpoint."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


@app.middleware("http")
async def common_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.get("/", response_class=HTMLResponse)
def home():
    page = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    canonical = f'<link rel="canonical" href="{html.escape(site_absolute_url("/"), quote=True)}">' if SITE_URL else ""
    og_url = f'<meta property="og:url" content="{html.escape(site_absolute_url("/"), quote=True)}">' if SITE_URL else ""
    structured = ""
    if SITE_URL:
        structured = "<script type=\"application/ld+json\">" + json.dumps({
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": "OptiSolve",
            "url": site_absolute_url("/"),
            "applicationCategory": "EducationalApplication",
            "operatingSystem": "Any",
            "description": "An interactive linear programming solver with Simplex, Two-Phase, Big-M, algorithm traces, and generated visual explanations.",
        }, ensure_ascii=False) + "</script>"
    page = page.replace("<!-- OPTISOLVE_CANONICAL -->", canonical)
    page = page.replace("<!-- OPTISOLVE_OG_URL -->", og_url)
    page = page.replace("<!-- OPTISOLVE_STRUCTURED_DATA -->", structured)
    return HTMLResponse(page)


@app.get("/favicon.svg")
def favicon():
    return FileResponse(ROOT / "favicon.svg", media_type="image/svg+xml")


@app.get("/about", response_class=HTMLResponse)
def about_page():
    page = (ROOT / "frontend" / "about.html").read_text(encoding="utf-8")
    if SITE_URL:
        page = page.replace("<!-- OPTISOLVE_CANONICAL -->", f'<link rel="canonical" href="{html.escape(site_absolute_url("/about"), quote=True)}">')
    else:
        page = page.replace("<!-- OPTISOLVE_CANONICAL -->", "")
    return HTMLResponse(page)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    page = (ROOT / "frontend" / "privacy.html").read_text(encoding="utf-8")
    if SITE_URL:
        page = page.replace("<!-- OPTISOLVE_CANONICAL -->", f'<link rel="canonical" href="{html.escape(site_absolute_url("/privacy"), quote=True)}">')
    else:
        page = page.replace("<!-- OPTISOLVE_CANONICAL -->", "")
    return HTMLResponse(page)


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /docs",
        "Disallow: /redoc",
        "Disallow: /openapi.json",
        "Disallow: /solve",
        "Disallow: /parse-problem",
        "Disallow: /video-health",
        "Disallow: /capabilities",
        "Disallow: /jobs/",
    ]
    if SITE_URL:
        lines.append(f"Sitemap: {site_absolute_url('/sitemap.xml')}")
    return "\n".join(lines) + "\n"


@app.get("/sitemap.xml")
def sitemap_xml():
    if not SITE_URL:
        raise HTTPException(503, "Set OPTISOLVE_BASE_URL to the public HTTPS origin before publishing the sitemap.")
    location = html.escape(site_absolute_url("/"), quote=True)
    locations = [site_absolute_url("/"), site_absolute_url("/about"), site_absolute_url("/privacy")]
    url_items = "".join(f"<url><loc>{html.escape(url, quote=True)}</loc></url>" for url in locations)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'{url_items}'
        '</urlset>'
    )
    return Response(content=body, media_type="application/xml")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "solver_binary_available": BINARY.is_file()}


@app.get("/video-health")
def video_health():
    """Report the local tools needed to render real graph and trace MP4 files."""
    tools = {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "latex": shutil.which("latex"),
        "dvisvgm": shutil.which("dvisvgm"),
    }
    return {
        "manim": {"path": str(MANIM), "available": MANIM.is_file()},
        "scenes": {
            "graph": {"path": str(ANIMATION), "available": ANIMATION.is_file()},
            "algorithm_trace": {"path": str(TRACE_ANIMATION), "available": TRACE_ANIMATION.is_file()},
        },
        "tools": {name: {"path": path, "available": bool(path)} for name, path in tools.items()},
        "expected_outputs": {
            "graph": "runtime/jobs/<job-id>/media/videos/lpp_animation/480p15/LPPAnimation.mp4",
            "algorithm_trace": "runtime/jobs/<job-id>/media/videos/algorithm_trace_animation/480p15/AlgorithmTraceAnimation.mp4",
        },
        "note": "Each solve uses a separate workspace; run a real solve to verify MP4 rendering.",
    }


@app.post("/parse-problem")
def parse_problem(request: NaturalLanguageRequest):
    """Extract an editable LP model from formula-style plain language.

    This is deliberately a conservative parser, not a claim to understand
    arbitrary business stories. The resulting model must be reviewed by the
    user before it is submitted to /solve.
    """
    try:
        model = parse_natural_language_problem(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "model": model,
        "review_required": True,
        "message": "Draft model extracted. Review every coefficient, relation, and RHS before solving.",
    }


@app.get("/capabilities")
def capabilities():
    return {
        "max_variables": MAX_VARIABLES,
        "max_constraints": MAX_CONSTRAINTS,
        "natural_language_parser": "conservative formula-style parser; explicit LP equations phrased with math words; requires user review; does not infer arbitrary business prose",
        "natural_language_endpoint": "/parse-problem",
        "coefficients": "any finite real value; no arbitrary 1..50 limit",
        "variable_domain": "nonnegative variables; redundant explicit x_i >= 0 rows are recognized and removed before solving",
        "redundant_nonnegativity_rows": "positive multiples of a single variable >= 0 are treated as built-in variable bounds",
        "methods": {
            "simplex": "max/min with <= constraints and nonnegative RHS",
            "two-phase": "max/min with <=, >=, = constraints and signed RHS",
            "big-m": "max/min with <=, >=, = constraints and signed RHS",
        },
        "graph_visualizer": "supports exactly two variables with <=, >=, and = constraints, signed RHS values, and nonnegative variable domains; the displayed view is clipped to its plotting window",
        "algorithm_trace_video": "tableau trace animation for supported recorded trace events; larger tableaus may be summarized for readability",
    }


@app.post("/solve")
def solve(problem: LPPRequest, _guard: None = Depends(solve_guard)):
    sense = normalize_sense(problem.sense)
    method_arg, _ = normalize_method(problem.method)
    variable_count = len(problem.objective_coefficients)

    for index, constraint in enumerate(problem.constraints, start=1):
        if len(constraint.coefficients) != variable_count:
            raise HTTPException(
                400,
                f"Constraint {index} has {len(constraint.coefficients)} coefficients; "
                f"expected {variable_count} to match the objective function.",
            )
        if constraint.relation not in {"<=", ">=", "="}:
            raise HTTPException(400, "Relations must be <=, >=, or =.")

    values = list(problem.objective_coefficients)
    for constraint in problem.constraints:
        values.extend(constraint.coefficients)
        values.append(constraint.rhs)
    if not all(math.isfinite(value) for value in values):
        raise HTTPException(400, "All coefficients and RHS values must be finite numbers.")

    effective_constraints = [
        constraint for constraint in problem.constraints
        if not is_explicit_nonnegativity_bound(constraint)
    ]
    ignored_nonnegativity_count = len(problem.constraints) - len(effective_constraints)
    if not effective_constraints:
        raise HTTPException(
            400,
            "Add at least one structural constraint besides explicit x_i >= 0 bounds; "
            "non-negativity is already built into OptiSolve.",
        )

    if method_arg == "simplex":
        if any(c.relation != "<=" for c in effective_constraints):
            raise HTTPException(
                400,
                "Standard Simplex requires <= constraints. Explicit x_i >= 0 bounds are ignored automatically; use Two-Phase or Big-M for other >= and = constraints.",
            )
        if any(c.rhs < 0 for c in effective_constraints):
            raise HTTPException(
                400,
                "Standard Simplex requires nonnegative right-hand sides. Use Two-Phase or Big-M for negative RHS values.",
            )

    lines = [
        sense,
        str(variable_count),
        str(len(effective_constraints)),
        " ".join(number(value) for value in problem.objective_coefficients),
    ]
    for constraint in effective_constraints:
        coefficients = " ".join(number(value) for value in constraint.coefficients)
        lines.append(f"{coefficients} {constraint.relation} {number(constraint.rhs)}")

    cleanup_old_jobs()
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    result_file = job_dir / "optisolve_result.json"
    media_dir = job_dir / "media"
    graph_video = job_video_path(job_dir, "lpp_animation", "LPPAnimation")
    trace_video = job_video_path(job_dir, "algorithm_trace_animation", "AlgorithmTraceAnimation")

    try:
        process = subprocess.run(
            [str(BINARY), "--algorithm", method_arg],
            input="\n".join(lines) + "\n",
            text=True,
            capture_output=True,
            cwd=job_dir,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "The solver timed out.")

    if process.returncode != 0:
        raise HTTPException(500, "C++ solver failed: " + process.stderr[-1500:])

    try:
        with result_file.open("r", encoding="utf-8") as file:
            result = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"Could not read solver result: {exc}")

    # New algorithm trace video: works for all variable counts and methods when
    # the C++ solver recorded trace events. It is independent of the 2D graph.
    trace_video_url = None
    trace_video_error = None
    trace_video_status = "not_available"
    trace = result.get("trace")
    if isinstance(trace, list) and trace:
        ok, error = run_manim(
            TRACE_ANIMATION, "AlgorithmTraceAnimation",
            result_json=result_file, media_dir=media_dir, timeout=180,
        )
        if ok and nonempty_video(trace_video):
            trace_video_url = f"/jobs/{job_id}/trace-video"
            trace_video_status = "generated"
        else:
            trace_video_status = "failed"
            trace_video_error = error or "Manim finished without creating a non-empty algorithm-trace MP4."

    status = str(result.get("status", "")).lower()
    solution = result.get("solution")
    if status != "optimal" or solution is None:
        message = result.get("message", "No optimal solution was found.")
        message = add_nonnegativity_notice(message, ignored_nonnegativity_count)
        if trace_video_url:
            message += " The algorithm trace animation is available."
        if trace_video_error:
            message += " The numerical trace is available on the page, but its MP4 could not be generated."
        return {
            "result": result,
            "job_id": job_id,
            "video_url": None,
            "trace_video_url": trace_video_url,
            "trace_video_status": trace_video_status,
            "trace_video_error": trace_video_error,
            "video_status": "not_applicable",
            "video_error": None,
            "message": message,
            "ignored_redundant_nonnegativity_constraints": ignored_nonnegativity_count,
        }

    if variable_count != 2:
        message = (
            "Numerical solution calculated successfully. The current graphical visualizer "
            "supports exactly two decision variables; higher-dimensional problems are solved numerically."
        )
        message = add_nonnegativity_notice(message, ignored_nonnegativity_count)
        if trace_video_url:
            message += " The algorithm trace animation is available."
        if trace_video_error:
            message += " The full algorithm trace remains available in the webpage."
        return {
            "result": result,
            "job_id": job_id,
            "video_url": None,
            "trace_video_url": trace_video_url,
            "trace_video_status": trace_video_status,
            "trace_video_error": trace_video_error,
            "video_status": "not_applicable",
            "video_error": None,
            "message": message,
            "ignored_redundant_nonnegativity_constraints": ignored_nonnegativity_count,
        }

    # Generate a graphical explanation for every two-variable optimal model.
    # The graph scene handles <=, >=, = and signed RHS values. Higher-dimensional
    # models retain their numerical result and algorithm trace without a 2D graph.
    graph_ok, graph_error = run_manim(
        ANIMATION, "LPPAnimation",
        result_json=result_file, media_dir=media_dir, timeout=180,
    )
    if not graph_ok or not nonempty_video(graph_video):
        return {
            "result": result,
            "job_id": job_id,
            "video_url": None,
            "trace_video_url": trace_video_url,
            "trace_video_status": trace_video_status,
            "trace_video_error": trace_video_error,
            "video_status": "failed",
            "video_error": graph_error or "Manim did not create a non-empty graph MP4.",
            "message": add_nonnegativity_notice(
                "The numerical solution was found, but the graph animation failed. "
                + (graph_error or "Manim did not create a non-empty MP4."),
                ignored_nonnegativity_count,
            ),
            "ignored_redundant_nonnegativity_constraints": ignored_nonnegativity_count,
        }

    if trace_video_url:
        message = "Solution, algorithm trace animation, and graphical explanation generated successfully."
    elif trace_video_error:
        message = "Solution and graph animation generated; the algorithm trace is visible on the webpage but its MP4 failed."
    else:
        message = "Solution and graph animation generated successfully."
    message = add_nonnegativity_notice(message, ignored_nonnegativity_count)

    return {
        "result": result,
        "job_id": job_id,
        "video_url": f"/jobs/{job_id}/video",
        "trace_video_url": trace_video_url,
        "trace_video_status": trace_video_status,
        "trace_video_error": trace_video_error,
        "video_status": "generated",
        "video_error": None,
        "message": message,
        "ignored_redundant_nonnegativity_constraints": ignored_nonnegativity_count,
    }


@app.get("/jobs/{job_id}/video")
def get_job_video(job_id: str):
    job_dir = get_job_directory(job_id)
    video = job_video_path(job_dir, "lpp_animation", "LPPAnimation")
    if not nonempty_video(video):
        raise HTTPException(404, "Graph video not found or expired for this solve.")
    return FileResponse(
        video, media_type="video/mp4", filename=f"optisolve-{job_id}.mp4",
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )


@app.get("/jobs/{job_id}/trace-video")
def get_job_trace_video(job_id: str):
    job_dir = get_job_directory(job_id)
    video = job_video_path(job_dir, "algorithm_trace_animation", "AlgorithmTraceAnimation")
    if not nonempty_video(video):
        raise HTTPException(404, "Algorithm trace video not found or expired for this solve.")
    return FileResponse(
        video, media_type="video/mp4", filename=f"optisolve-trace-{job_id}.mp4",
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )
