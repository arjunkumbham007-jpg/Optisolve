import pytest

from visualizer.lpp_highdim_animation import constraint_diagnostics, objective_contributions


def test_objective_contributions_are_calculated_per_variable():
    assert objective_contributions([40, 25, -2], [6, 12, 3]) == [240.0, 300.0, -6.0]


def test_objective_contributions_reject_mismatched_lengths():
    with pytest.raises(ValueError, match="equal length"):
        objective_contributions([3, 2], [1])


def test_constraint_diagnostics_calculates_slack_and_utilization():
    result = constraint_diagnostics(
        [{"coefficients": [2, 1], "relation": "<=", "rhs": 30}],
        [6, 12],
    )[0]
    assert result["lhs"] == 24.0
    assert result["balance_label"] == "Slack"
    assert result["balance"] == 6.0
    assert result["utilization_percent"] == 80.0
    assert result["satisfied"] is True


def test_constraint_diagnostics_calculates_surplus_and_equality_residual():
    results = constraint_diagnostics(
        [
            {"coefficients": [1, 1], "relation": ">=", "rhs": 10},
            {"coefficients": [1, -1], "relation": "=", "rhs": -6},
        ],
        [6, 12],
    )
    assert results[0]["balance_label"] == "Surplus"
    assert results[0]["balance"] == 8.0
    assert results[0]["utilization_percent"] is None
    assert results[0]["satisfied"] is True
    assert results[1]["balance_label"] == "Residual"
    assert results[1]["balance"] == 0.0
    assert results[1]["satisfied"] is True


def test_constraint_diagnostics_flags_violations_and_dimension_mismatch():
    bad = constraint_diagnostics(
        [{"coefficients": [1, 1], "relation": "<=", "rhs": 5}],
        [6, 2],
    )[0]
    assert bad["satisfied"] is False
    with pytest.raises(ValueError, match="exactly 2 coefficients"):
        constraint_diagnostics(
            [{"coefficients": [1], "relation": "<=", "rhs": 5}],
            [1, 2],
        )
