import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.natural_language import parse_natural_language_problem

client = TestClient(app)


def test_parses_symbolic_multiline_problem():
    parsed = parse_natural_language_problem(
        """Maximize Z = 3x1 + 2x2
        Subject to:
        x1 + x2 <= 4
        x1 >= 1
        x2 >= 1"""
    )
    assert parsed["sense"] == "max"
    assert parsed["objective_coefficients"] == [3.0, 2.0]
    assert parsed["constraints"] == [
        {"coefficients": [1.0, 1.0], "relation": "<=", "rhs": 4.0},
        {"coefficients": [1.0, 0.0], "relation": ">=", "rhs": 1.0},
        {"coefficients": [0.0, 1.0], "relation": ">=", "rhs": 1.0},
    ]
    assert parsed["variable_count"] == 2


def test_parses_math_words_and_semicolon_separators():
    parsed = parse_natural_language_problem(
        "Maximize 3 times x1 plus 2 times x2 subject to "
        "x1 plus x2 at most 4; x1 at least 1; x2 at least 1"
    )
    assert parsed["objective_coefficients"] == [3.0, 2.0]
    assert [row["relation"] for row in parsed["constraints"]] == ["<=", ">=", ">="]
    assert [row["rhs"] for row in parsed["constraints"]] == [4.0, 1.0, 1.0]


def test_parses_minimization_negative_rhs_and_three_variables():
    parsed = parse_natural_language_problem(
        "Minimize cost = 2x1 minus 5x2 plus x3 such that "
        "-x1 less than or equal to -3 and x2 no more than 10 and x3 equals 4"
    )
    assert parsed["sense"] == "min"
    assert parsed["objective_coefficients"] == [2.0, -5.0, 1.0]
    assert parsed["constraints"] == [
        {"coefficients": [-1.0, 0.0, 0.0], "relation": "<=", "rhs": -3.0},
        {"coefficients": [0.0, 1.0, 0.0], "relation": "<=", "rhs": 10.0},
        {"coefficients": [0.0, 0.0, 1.0], "relation": "=", "rhs": 4.0},
    ]


def test_expands_grouped_nonnegative_bounds():
    parsed = parse_natural_language_problem(
        "Maximize x1 + x2 subject to x1 + x2 <= 5; x1, x2 >= 0"
    )
    assert parsed["constraints"][-2:] == [
        {"coefficients": [1.0, 0.0], "relation": ">=", "rhs": 0.0},
        {"coefficients": [0.0, 1.0], "relation": ">=", "rhs": 0.0},
    ]


def test_parser_endpoint_returns_review_required_draft():
    response = client.post(
        "/parse-problem",
        json={"text": "Maximize Z = 4x1 + 3x2 subject to x1 + x2 <= 4; x1 <= 2; x2 <= 3"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["review_required"] is True
    assert data["model"]["objective_coefficients"] == [4.0, 3.0]
    assert data["model"]["constraint_count"] == 3
    assert "Review every coefficient" in data["message"]


def test_parser_endpoint_rejects_missing_subject_to():
    response = client.post("/parse-problem", json={"text": "Maximize Z = 3x1 + 2x2"})
    assert response.status_code == 400
    assert "subject to" in response.json()["detail"]


def test_parser_rejects_nonlinear_product():
    with pytest.raises(ValueError, match="Unsupported expression"):
        parse_natural_language_problem(
            "Maximize Z = x1 * x2 subject to x1 + x2 <= 5"
        )


def test_parser_documents_scope_and_review_in_capabilities():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["natural_language_endpoint"] == "/parse-problem"
    assert "does not infer arbitrary business prose" in data["natural_language_parser"]
