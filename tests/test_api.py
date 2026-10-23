import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api

client = TestClient(api.app)


def example_payload():
    return {
        "sense": "max",
        "method": "simplex",
        "objective_coefficients": [4, 3],
        "constraints": [
            {"coefficients": [1, 1], "relation": "<=", "rhs": 4},
            {"coefficients": [1, 0], "relation": "<=", "rhs": 2},
            {"coefficients": [0, 1], "relation": "<=", "rhs": 3},
        ],
    }


def fake_result_from_stdin(stdin_text):
    """Create a schema-consistent fake solver result from the C++ input protocol."""
    lines = [line.strip() for line in stdin_text.splitlines() if line.strip()]
    sense = lines[0].lower()
    n = int(lines[1])
    m = int(lines[2])
    objective = [float(value) for value in lines[3].split()]
    constraints = []

    for line in lines[4:4 + m]:
        tokens = line.split()
        constraints.append({
            "coefficients": [float(value) for value in tokens[:n]],
            "relation": tokens[n],
            "rhs": float(tokens[n + 1]),
        })

    # Known test solutions for the requests used below. Other fake cases use
    # zero values because these tests validate API routing, not optimization.
    if n == 2 and objective == [4.0, 3.0] and len(constraints) == 3:
        variables = [2.0, 2.0]
    elif n == 2 and objective == [1.0, 1.0] and any(
        c["coefficients"] == [-1.0, 0.0] and c["relation"] == "<=" and c["rhs"] == -1.0
        for c in constraints
    ):
        variables = [3.0, 2.0]
    elif n == 3 and objective == [1.0, 1.0, 1.0]:
        variables = [2.0, 3.0, 4.0]
    else:
        variables = [0.0] * n

    # A nonnegative-variable model with a nonnegative-coefficient <= row and
    # negative RHS is visibly infeasible (LHS cannot be negative).
    obviously_infeasible = any(
        constraint["relation"] == "<="
        and constraint["rhs"] < 0
        and all(value >= 0 for value in constraint["coefficients"])
        for constraint in constraints
    )
    z = sum(c * x for c, x in zip(objective, variables))
    status = "infeasible" if obviously_infeasible else "optimal"
    if obviously_infeasible:
        variables = None
    return {
        "schema_version": 1,
        "status": status,
        "method": "simplex",
        "message": "Infeasible model." if obviously_infeasible else "Optimal solution found.",
        "iterations": 2,
        "model": {
            "sense": "maximize" if sense == "max" else "minimize",
            "variable_names": [f"x{i + 1}" for i in range(n)],
            "objective_coefficients": objective,
            "nonnegative_variables": True,
            "constraints": constraints,
        },
        "solution": None if variables is None else {"objective_value": z, "variables": variables},
        "trace_truncated": False,
        "trace": [
            {
                "phase": "simplex",
                "event": "phase_start",
                "iteration": 0,
                "explanation": "Initial tableau prepared by the solver.",
                "column_names": [],
                "basis": [],
                "tableau_recorded": False,
                "tableau": None,
                "entering_variable": None,
                "leaving_variable": None,
                "pivot_row": None,
                "pivot_column": None,
                "pivot_value": None,
                "ratio_tests": [],
                "reduced_costs": [],
                "row_operations": [],
            },
            {
                "phase": "simplex",
                "event": "pivot",
                "iteration": 1,
                "explanation": "Apply the minimum-ratio test.",
                "column_names": ["x1", "x2", "s1", "s2", "s3"],
                "basis": ["s1", "s2", "s3"],
                "tableau_recorded": False,
                "tableau": None,
                "entering_variable": "x1",
                "leaving_variable": "s2",
                "pivot_row": 2,
                "pivot_column": 1,
                "pivot_value": 1.0,
                "ratio_tests": [
                    {"basic_variable": "s1", "rhs": 4.0, "entering_coefficient": 1.0, "eligible": True, "ratio": 4.0},
                    {"basic_variable": "s2", "rhs": 2.0, "entering_coefficient": 1.0, "eligible": True, "ratio": 2.0},
                    {"basic_variable": "s3", "rhs": 3.0, "entering_coefficient": 0.0, "eligible": False, "ratio": None},
                ],
                "reduced_costs": [
                    {"variable": "x1", "tableau_coefficient": -4.0, "eligible": True, "selected": True, "artificial": False},
                    {"variable": "x2", "tableau_coefficient": -3.0, "eligible": True, "selected": False, "artificial": False},
                    {"variable": "s1", "tableau_coefficient": 0.0, "eligible": False, "selected": False, "artificial": False},
                ],
                "row_operations": [
                    {"target_row": 2, "source_row": 2, "operation": "divide", "factor": 1.0},
                    {"target_row": 1, "source_row": 2, "operation": "subtract_multiple", "factor": 1.0},
                    {"target_row": 4, "source_row": 2, "operation": "subtract_multiple", "factor": -4.0},
                ],
            }
        ],
    }


@pytest.fixture
def mock_pipeline(monkeypatch, tmp_path):
    binary = tmp_path / "optisolve"
    binary.write_text("test placeholder", encoding="utf-8")
    manim = tmp_path / "manim"
    manim.write_text("test placeholder", encoding="utf-8")
    trace_animation = tmp_path / "algorithm_trace_animation.py"
    graph_animation = tmp_path / "lpp_animation.py"
    trace_animation.write_text("# mocked scene path", encoding="utf-8")
    graph_animation.write_text("# mocked graph scene path", encoding="utf-8")
    jobs_dir = tmp_path / "jobs"
    monkeypatch.setattr(api, "BINARY", binary)
    monkeypatch.setattr(api, "MANIM", manim)
    monkeypatch.setattr(api, "TRACE_ANIMATION", trace_animation)
    monkeypatch.setattr(api, "ANIMATION", graph_animation)
    monkeypatch.setattr(api, "JOBS_DIR", jobs_dir)

    calls = []
    inputs = []
    outputs = []

    def fake_run(args, **kwargs):
        calls.append(args)
        inputs.append(kwargs.get("input", ""))
        if args[0] == str(binary):
            result_file = Path(kwargs["cwd"]) / "optisolve_result.json"
            result_file.write_text(
                json.dumps(fake_result_from_stdin(kwargs.get("input", ""))),
                encoding="utf-8",
            )
        else:
            media_dir = Path(args[args.index("--media_dir") + 1])
            scene_file = Path(args[-2])
            scene_name = args[-1]
            output_path = media_dir / "videos" / scene_file.stem / "480p15" / f"{scene_name}.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            prefix = "test trace video" if scene_name == "AlgorithmTraceAnimation" else "test graph video"
            output_path.write_bytes(f"{prefix}:{media_dir.parent.name}".encode("utf-8"))
            outputs.append(output_path)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    return {"calls": calls, "inputs": inputs, "jobs_dir": jobs_dir, "outputs": outputs}


def test_homepage_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Optimization, explained." in response.text
    assert 'id="method"' in response.text
    assert 'id="variable-count"' in response.text
    assert "up to 100" in response.text
    assert 'id="check-video-health"' in response.text
    assert 'name="description"' in response.text
    assert 'An interactive linear programming solver' in response.text
    assert 'href="/about"' in response.text


def test_seo_files_are_served():
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")
    assert "User-agent: *" in client.get("/robots.txt").text


def test_video_health_endpoint_reports_local_prerequisites():
    response = client.get("/video-health")
    assert response.status_code == 200
    data = response.json()
    assert "manim" in data and "available" in data["manim"]
    assert data["scenes"]["graph"]["available"] is True
    assert data["scenes"]["algorithm_trace"]["available"] is True
    assert set(data["tools"]) == {"ffmpeg", "ffprobe", "latex", "dvisvgm"}
    assert "graph" in data["expected_outputs"]
    assert "algorithm_trace" in data["expected_outputs"]


def test_capabilities_endpoint_documents_limits():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["max_variables"] == 20
    assert data["max_constraints"] == 100
    assert "no arbitrary 1..50 limit" in data["coefficients"]
    assert "recognized and removed" in data["variable_domain"]


def test_rejects_unsupported_constraint_for_standard_simplex():
    payload = example_payload()
    payload["constraints"][0]["relation"] = ">="
    response = client.post("/solve", json=payload)
    assert response.status_code == 400
    assert "Two-Phase or Big-M" in response.json()["detail"]


def test_standard_simplex_ignores_explicit_nonnegativity_bounds(mock_pipeline):
    payload = example_payload()
    payload["constraints"].extend([
        {"coefficients": [1, 0], "relation": ">=", "rhs": 0},
        {"coefficients": [0, 1], "relation": ">=", "rhs": 0},
    ])

    response = client.post("/solve", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["ignored_redundant_nonnegativity_constraints"] == 2
    assert "Ignored 2 explicit non-negativity constraints" in data["message"]
    sent_lines = mock_pipeline["inputs"][0].splitlines()
    assert sent_lines[0:3] == ["max", "2", "3"]
    assert len(sent_lines) == 7  # 4 header/objective lines plus 3 structural rows
    assert all(">=" not in line for line in sent_lines[4:])


def test_standard_simplex_does_not_strip_nonredundant_ge_row(mock_pipeline):
    payload = example_payload()
    payload["constraints"].append(
        {"coefficients": [-1, 0], "relation": ">=", "rhs": 0}
    )

    response = client.post("/solve", json=payload)

    assert response.status_code == 400
    assert "Standard Simplex requires <= constraints" in response.json()["detail"]
    assert mock_pipeline["calls"] == []


def test_rejects_model_containing_only_nonnegativity_bounds():
    payload = {
        "sense": "max",
        "method": "simplex",
        "objective_coefficients": [1, 1],
        "constraints": [
            {"coefficients": [1, 0], "relation": ">=", "rhs": 0},
            {"coefficients": [0, 1], "relation": ">=", "rhs": 0},
        ],
    }
    response = client.post("/solve", json=payload)
    assert response.status_code == 400
    assert "at least one structural constraint" in response.json()["detail"]


def test_rejects_negative_rhs_for_standard_simplex():
    payload = example_payload()
    payload["constraints"][0]["rhs"] = -1
    response = client.post("/solve", json=payload)
    assert response.status_code == 400
    assert "nonnegative" in response.json()["detail"]


def test_rejects_constraint_dimension_mismatch():
    payload = example_payload()
    payload["constraints"][0]["coefficients"] = [1, 2, 3]
    response = client.post("/solve", json=payload)
    assert response.status_code == 400
    assert "expected 2" in response.json()["detail"]


def test_rejects_too_many_variables():
    payload = {
        "sense": "max",
        "method": "two-phase",
        "objective_coefficients": [1.0] * 21,
        "constraints": [{"coefficients": [1.0] * 21, "relation": "=", "rhs": 1}],
    }
    response = client.post("/solve", json=payload)
    assert response.status_code == 422


def test_rejects_more_than_100_constraints():
    payload = example_payload()
    payload["constraints"] = [
        {"coefficients": [1, 0], "relation": "=", "rhs": 1}
        for _ in range(101)
    ]
    response = client.post("/solve", json=payload)
    assert response.status_code == 422


def test_successful_solve_and_video(mock_pipeline):
    response = client.post("/solve", json=example_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"] == "optimal"
    assert data["result"]["solution"]["objective_value"] == 14
    assert data["result"]["solution"]["variables"] == [2, 2]
    assert data["job_id"]
    assert data["video_url"] == f"/jobs/{data['job_id']}/video"
    assert data["trace_video_url"] == f"/jobs/{data['job_id']}/trace-video"
    assert data["video_status"] == "generated"
    assert data["trace_video_status"] == "generated"
    assert data["video_error"] is None
    assert data["trace_video_error"] is None
    assert len(mock_pipeline["calls"]) == 3
    assert mock_pipeline["calls"][0][1:] == ["--algorithm", "simplex"]
    assert mock_pipeline["calls"][1][-1] == "AlgorithmTraceAnimation"

    trace_response = client.get(data["trace_video_url"])
    assert trace_response.status_code == 200
    assert trace_response.content == f"test trace video:{data['job_id']}".encode("utf-8")
    assert trace_response.headers.get("x-robots-tag") == "noindex, nofollow"

    video_response = client.get(data["video_url"])
    assert video_response.status_code == 200
    assert video_response.content == f"test graph video:{data['job_id']}".encode("utf-8")
    assert video_response.headers.get("x-robots-tag") == "noindex, nofollow"


def test_three_variables_are_passed_to_cpp_and_skip_2d_video(mock_pipeline):
    payload = {
        "sense": "max",
        "method": "two-phase",
        "objective_coefficients": [1, 1, 1],
        "constraints": [
            {"coefficients": [1, 0, 0], "relation": "<=", "rhs": 2},
            {"coefficients": [0, 1, 0], "relation": "<=", "rhs": 3},
            {"coefficients": [0, 0, 1], "relation": "<=", "rhs": 4},
            {"coefficients": [1, 1, 1], "relation": "<=", "rhs": 9},
        ],
    }
    response = client.post("/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["solution"]["variables"] == [2, 3, 4]
    assert data["result"]["solution"]["objective_value"] == 9
    assert data["video_url"] is None
    assert data["video_status"] == "not_applicable"
    assert data["trace_video_url"] == f"/jobs/{data['job_id']}/trace-video"
    assert "exactly two decision variables" in data["message"]
    assert len(mock_pipeline["calls"]) == 2
    input_lines = mock_pipeline["inputs"][0].splitlines()
    assert input_lines[0:3] == ["max", "3", "4"]
    assert input_lines[3] == "1 1 1"


def test_accepts_fractional_negative_and_large_coefficients(mock_pipeline):
    payload = {
        "sense": "max",
        "method": "two-phase",
        "objective_coefficients": [125.5, -2.75],
        "constraints": [
            {"coefficients": [-2.5, 7.25], "relation": ">=", "rhs": -12.5},
        ],
    }
    response = client.post("/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["video_url"] == f"/jobs/{data['job_id']}/video"
    sent_input = mock_pipeline["inputs"][0]
    assert "125.5 -2.75" in sent_input
    assert "-2.5 7.25 >= -12.5" in sent_input


def test_accepts_20_variables_and_100_constraints(mock_pipeline):
    variable_count = 20
    coefficients = [1] + [0] * (variable_count - 1)
    payload = {
        "sense": "max",
        "method": "two-phase",
        "objective_coefficients": [1] * variable_count,
        "constraints": [
            {"coefficients": coefficients, "relation": "=", "rhs": i + 1}
            for i in range(100)
        ],
    }
    response = client.post("/solve", json=payload)
    assert response.status_code == 200
    assert response.json()["video_url"] is None
    input_lines = mock_pipeline["inputs"][0].splitlines()
    assert input_lines[0:3] == ["max", "20", "100"]
    assert input_lines[3] == " ".join(["1"] * 20)
    assert len(input_lines) == 4 + 100
    assert all(len(line.split()) == 22 for line in input_lines[4:])


def test_two_phase_mixed_constraints_get_graph_and_trace_videos(mock_pipeline):
    payload = example_payload()
    payload["method"] = "two-phase"
    payload["constraints"][1] = {"coefficients": [1, 0], "relation": ">=", "rhs": 1}
    response = client.post("/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"] == "optimal"
    assert data["job_id"]
    assert data["video_url"] == f"/jobs/{data['job_id']}/video"
    assert data["trace_video_url"] == f"/jobs/{data['job_id']}/trace-video"
    assert "graphical explanation generated successfully" in data["message"]
    assert len(mock_pipeline["calls"]) == 3
    assert mock_pipeline["calls"][0][1:] == ["--algorithm", "two-phase"]
    assert mock_pipeline["calls"][1][-1] == "AlgorithmTraceAnimation"
    assert mock_pipeline["calls"][2][-1] == "LPPAnimation"


def test_negative_rhs_is_accepted_by_two_phase(mock_pipeline):
    payload = example_payload()
    payload["method"] = "two-phase"
    payload["constraints"][0]["rhs"] = -1
    response = client.post("/solve", json=payload)
    assert response.status_code == 200
    assert response.json()["video_url"] is None
    assert response.json()["trace_video_url"] == f"/jobs/{response.json()['job_id']}/trace-video"
    assert len(mock_pipeline["calls"]) == 2



def test_two_phase_feasible_negative_rhs_gets_graph_video(mock_pipeline):
    payload = {
        "sense": "max",
        "method": "two-phase",
        "objective_coefficients": [1, 1],
        "constraints": [
            {"coefficients": [-1, 0], "relation": "<=", "rhs": -1},
            {"coefficients": [1, 0], "relation": "<=", "rhs": 3},
            {"coefficients": [0, 1], "relation": "<=", "rhs": 2},
        ],
    }
    response = client.post("/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["solution"]["variables"] == [3.0, 2.0]
    assert data["job_id"]
    assert data["video_url"] == f"/jobs/{data['job_id']}/video"
    assert data["trace_video_url"] == f"/jobs/{data['job_id']}/trace-video"
    assert len(mock_pipeline["calls"]) == 3


def test_ratio_test_details_are_preserved_in_api_result(mock_pipeline):
    response = client.post("/solve", json=example_payload())

    assert response.status_code == 200
    result = response.json()["result"]
    pivot = next(step for step in result["trace"] if step["event"] == "pivot")
    assert pivot["entering_variable"] == "x1"
    assert pivot["leaving_variable"] == "s2"
    assert pivot["ratio_tests"][0]["ratio"] == 4.0
    assert pivot["ratio_tests"][1]["ratio"] == 2.0
    assert pivot["ratio_tests"][2]["eligible"] is False
    assert pivot["ratio_tests"][2]["ratio"] is None
    costs = pivot["reduced_costs"]
    assert costs[0]["variable"] == "x1"
    assert costs[0]["selected"] is True
    assert costs[0]["tableau_coefficient"] == -4.0
    operations = pivot["row_operations"]
    assert operations[0] == {
        "target_row": 2, "source_row": 2, "operation": "divide", "factor": 1.0
    }
    assert operations[1]["operation"] == "subtract_multiple"
    assert operations[2]["target_row"] == 4  # objective row, 1-based
    assert operations[2]["factor"] == -4.0


def test_nonoptimal_result_does_not_render_graph_video(monkeypatch, tmp_path):
    binary = tmp_path / "optisolve"
    binary.write_text("test placeholder", encoding="utf-8")
    manim = tmp_path / "manim"
    manim.write_text("test placeholder", encoding="utf-8")
    trace_animation = tmp_path / "algorithm_trace_animation.py"
    graph_animation = tmp_path / "lpp_animation.py"
    trace_animation.write_text("# fake trace scene", encoding="utf-8")
    graph_animation.write_text("# fake graph scene", encoding="utf-8")
    jobs_dir = tmp_path / "jobs"
    monkeypatch.setattr(api, "BINARY", binary)
    monkeypatch.setattr(api, "MANIM", manim)
    monkeypatch.setattr(api, "TRACE_ANIMATION", trace_animation)
    monkeypatch.setattr(api, "ANIMATION", graph_animation)
    monkeypatch.setattr(api, "JOBS_DIR", jobs_dir)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == str(binary):
            result_file = Path(kwargs["cwd"]) / "optisolve_result.json"
            result = fake_result_from_stdin(kwargs.get("input", ""))
            result["status"] = "infeasible"
            result["message"] = "Infeasible model."
            result["solution"] = None
            result_file.write_text(json.dumps(result), encoding="utf-8")
        elif args[-1] == "AlgorithmTraceAnimation":
            media_dir = Path(args[args.index("--media_dir") + 1])
            out = media_dir / "videos" / Path(args[-2]).stem / "480p15" / "AlgorithmTraceAnimation.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"test trace video")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    response = client.post("/solve", json=example_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"] == "infeasible"
    assert data["video_url"] is None
    assert data["trace_video_url"] == f"/jobs/{data['job_id']}/trace-video"
    assert len(calls) == 2
    assert calls[1][-1] == "AlgorithmTraceAnimation"
    assert not api.job_video_path(jobs_dir / data["job_id"], "lpp_animation", "LPPAnimation").exists()


def test_graph_render_failure_is_reported_without_stale_video(monkeypatch, tmp_path):
    binary = tmp_path / "optisolve"
    binary.write_text("test placeholder", encoding="utf-8")
    manim = tmp_path / "manim"
    manim.write_text("test placeholder", encoding="utf-8")
    trace_animation = tmp_path / "algorithm_trace_animation.py"
    graph_animation = tmp_path / "lpp_animation.py"
    trace_animation.write_text("# fake trace scene", encoding="utf-8")
    graph_animation.write_text("# fake graph scene", encoding="utf-8")
    jobs_dir = tmp_path / "jobs"
    monkeypatch.setattr(api, "BINARY", binary)
    monkeypatch.setattr(api, "MANIM", manim)
    monkeypatch.setattr(api, "TRACE_ANIMATION", trace_animation)
    monkeypatch.setattr(api, "ANIMATION", graph_animation)
    monkeypatch.setattr(api, "JOBS_DIR", jobs_dir)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == str(binary):
            result_file = Path(kwargs["cwd"]) / "optisolve_result.json"
            result_file.write_text(json.dumps(fake_result_from_stdin(kwargs.get("input", ""))), encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if args[-1] == "AlgorithmTraceAnimation":
            media_dir = Path(args[args.index("--media_dir") + 1])
            out = media_dir / "videos" / Path(args[-2]).stem / "480p15" / "AlgorithmTraceAnimation.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"fresh trace video")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="LaTeX rendering error")

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    response = client.post("/solve", json=example_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"] == "optimal"
    assert data["video_url"] is None
    assert data["video_status"] == "failed"
    assert "LaTeX rendering error" in data["video_error"]
    assert data["trace_video_url"] == f"/jobs/{data['job_id']}/trace-video"
    assert data["trace_video_status"] == "generated"
    assert not api.job_video_path(jobs_dir / data["job_id"], "lpp_animation", "LPPAnimation").exists()


def test_job_video_urls_do_not_cross_contaminate(mock_pipeline):
    first = client.post("/solve", json=example_payload()).json()
    second = client.post("/solve", json=example_payload()).json()
    assert first["job_id"] != second["job_id"]
    assert first["video_url"] != second["video_url"]
    assert client.get(first["video_url"]).content == f"test graph video:{first['job_id']}".encode("utf-8")
    assert client.get(second["video_url"]).content == f"test graph video:{second['job_id']}".encode("utf-8")
    assert client.get(first["trace_video_url"]).content == f"test trace video:{first['job_id']}".encode("utf-8")
    assert client.get(second["trace_video_url"]).content == f"test trace video:{second['job_id']}".encode("utf-8")
    assert first["trace_video_url"] != second["trace_video_url"]


def test_job_video_route_rejects_invalid_ids():
    assert client.get("/jobs/../../etc/passwd/video").status_code in {404, 405}
    assert client.get("/jobs/not-a-uuid/video").status_code == 404


def test_seo_metadata_and_sitemap(monkeypatch):
    monkeypatch.setattr(api, "SITE_URL", "https://optisolve.example")
    homepage = client.get("/")
    assert "<title>OptiSolve — Interactive Linear Programming Solver" in homepage.text
    assert 'rel="canonical" href="https://optisolve.example/"' in homepage.text
    assert '"@type": "WebApplication"' in homepage.text
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Sitemap: https://optisolve.example/sitemap.xml" in robots.text
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "https://optisolve.example/" in sitemap.text
    assert "https://optisolve.example/about" in sitemap.text
    assert "https://optisolve.example/privacy" in sitemap.text
    assert client.get("/about").status_code == 200
    assert client.get("/privacy").status_code == 200
