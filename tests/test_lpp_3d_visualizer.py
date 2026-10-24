import pytest

from visualizer.lpp_3d_animation import feasible_vertices_3d, is_bounded_3d


def test_bounded_unit_box_has_eight_feasible_vertices():
    constraints = [
        {"coefficients": [1, 0, 0], "relation": "<=", "rhs": 1},
        {"coefficients": [0, 1, 0], "relation": "<=", "rhs": 1},
        {"coefficients": [0, 0, 1], "relation": "<=", "rhs": 1},
    ]
    vertices = feasible_vertices_3d(constraints)
    assert len(vertices) == 8
    assert is_bounded_3d(constraints)
    assert (0.0, 0.0, 0.0) in vertices
    assert (1.0, 1.0, 1.0) in vertices


def test_nonnegative_prism_without_z_upper_bound_is_unbounded():
    constraints = [
        {"coefficients": [1, 0, 0], "relation": "<=", "rhs": 1},
        {"coefficients": [0, 1, 0], "relation": "<=", "rhs": 1},
    ]
    assert not is_bounded_3d(constraints)
    assert len(feasible_vertices_3d(constraints)) >= 4


def test_mixed_inequalities_and_equality_vertex_enumeration():
    constraints = [
        {"coefficients": [1, 0, 0], "relation": "=", "rhs": 1},
        {"coefficients": [0, 1, 0], "relation": "<=", "rhs": 2},
        {"coefficients": [0, 0, 1], "relation": "<=", "rhs": 3},
    ]
    vertices = feasible_vertices_3d(constraints)
    assert (1.0, 0.0, 0.0) in vertices
    assert (1.0, 2.0, 3.0) in vertices
    assert is_bounded_3d(constraints)
