#!/usr/bin/env python3
"""Real browser-to-solver-to-Manim smoke test against a running local API.

This intentionally renders real MP4s, so it is slower than pytest API tests.
Usage: python scripts/e2e_smoke_v14.py [base-url]
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def request_json(path: str, payload: dict | None = None) -> tuple[dict, dict[str, str]]:
    url = urljoin(BASE + "/", path.lstrip("/"))
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urlopen(req, timeout=300) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")), dict(response.headers.items())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach {BASE}. Start Uvicorn first. Underlying error: {exc}"
        ) from exc


def request_mp4(path: str) -> bytes:
    url = urljoin(BASE + "/", path.lstrip("/"))
    req = Request(url, headers={"Accept": "video/mp4"})
    try:
        with urlopen(req, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {detail}") from exc
    if "video/mp4" not in content_type:
        raise RuntimeError(f"{path} has unexpected Content-Type: {content_type}")
    if len(data) < 1000:
        raise RuntimeError(f"{path} returned an unexpectedly small MP4 ({len(data)} bytes)")
    # ISO BMFF files usually start with a box length followed by 'ftyp'.
    if data[4:8] != b"ftyp":
        raise RuntimeError(f"{path} does not look like an MP4 (missing ftyp box)")
    return data


def verify_duration(data: bytes, label: str) -> None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required for real video validation but was not found.")
    with tempfile.NamedTemporaryFile(suffix=".mp4") as handle:
        handle.write(data)
        handle.flush()
        completed = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", handle.name],
            text=True, capture_output=True, check=False, timeout=30,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"ffprobe rejected {label}: {completed.stderr.strip()}")
    try:
        duration = float(completed.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not read {label} duration: {completed.stdout!r}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"Invalid {label} duration: {duration}")
    print(f"[PASS] {label}: {len(data):,} bytes, {duration:.2f} seconds")


def main() -> int:
    print(f"OptiSolve real end-to-end smoke test: {BASE}")

    with urlopen(urljoin(BASE + "/", ""), timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")
        assert response.status == 200
    assert "OptiSolve" in html
    assert "Describe it in words" in html
    assert "Parse into model" in html
    assert 'name="description"' in html
    assert "An interactive linear programming solver" in html
    print("[PASS] Homepage serves the current frontend and crawlable metadata.")

    about = urlopen(urljoin(BASE + "/", "about"), timeout=15)
    assert about.status == 200 and "About OptiSolve" in about.read().decode("utf-8", errors="replace")
    privacy = urlopen(urljoin(BASE + "/", "privacy"), timeout=15)
    assert privacy.status == 200 and "Privacy notice" in privacy.read().decode("utf-8", errors="replace")
    robots = urlopen(urljoin(BASE + "/", "robots.txt"), timeout=15)
    assert robots.status == 200 and "User-agent: *" in robots.read().decode("utf-8", errors="replace")
    print("[PASS] About, privacy, and robots endpoints are reachable.")

    capabilities, _ = request_json("/capabilities")
    assert capabilities["max_variables"] == 20
    assert capabilities["max_constraints"] == 100
    assert {"simplex", "two-phase", "big-m"}.issubset(capabilities["methods"])
    print("[PASS] Capabilities endpoint reports expected limits and algorithms.")

    parser_input = {
        "text": "Maximize Z = 3x1 plus 2x2 subject to x1 plus x2 at most 4; x1 at least 1; x2 at least 1"
    }
    parsed, _ = request_json("/parse-problem", parser_input)
    assert parsed.get("review_required") is True
    model = parsed["model"]
    assert model["objective_coefficients"] == [3.0, 2.0]
    assert len(model["constraints"]) == 3
    print("[PASS] Natural-language endpoint extracts the reviewed LP draft.")

    health, _ = request_json("/video-health")
    if not health.get("manim", {}).get("available"):
        raise RuntimeError(f"Manim is unavailable according to /video-health: {health.get('manim')}")

    payload = {
        "sense": "max",
        "method": "two-phase",
        "objective_coefficients": [3, 2],
        "constraints": [
            {"coefficients": [1, 1], "relation": "<=", "rhs": 4},
            {"coefficients": [1, 0], "relation": ">=", "rhs": 1},
            {"coefficients": [0, 1], "relation": ">=", "rhs": 1},
        ],
    }
    solved, _ = request_json("/solve", payload)
    result = solved["result"]
    solution = result.get("solution")
    assert result.get("status") == "optimal", f"Unexpected solver status: {result.get('status')}"
    assert solution is not None, "Solver returned no solution."
    assert abs(solution["objective_value"] - 11.0) < 1e-7
    assert len(solution["variables"]) == 2
    assert abs(solution["variables"][0] - 3.0) < 1e-7
    assert abs(solution["variables"][1] - 1.0) < 1e-7
    print("[PASS] Real C++ solve returns x1=3, x2=1, Z=11.")

    if not solved.get("video_url") or not solved.get("trace_video_url"):
        raise RuntimeError(
            "Solve succeeded, but both videos were not generated. "
            f"graph_status={solved.get('video_status')}, graph_error={solved.get('video_error')}; "
            f"trace_status={solved.get('trace_video_status')}, trace_error={solved.get('trace_video_error')}"
        )

    graph = request_mp4(solved["video_url"])
    verify_duration(graph, "graph explanation video")
    trace = request_mp4(solved["trace_video_url"])
    verify_duration(trace, "algorithm trace video")

    print("\nSUCCESS: parse -> C++ solve -> real Manim renders -> MP4 endpoints all passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
