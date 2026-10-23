from visualizer.lpp_geometry import (
    actual_vertices,
    boundary_segment,
    clip_region,
    feasible_viewport_points,
    point_satisfies_constraints,
    polygon_area,
)


def point_set(points):
    return {(round(x, 6), round(y, 6)) for x, y in points}


def test_original_le_problem_vertices():
    constraints = [
        {"coefficients": [1, 0], "relation": "<=", "rhs": 4},
        {"coefficients": [0, 2], "relation": "<=", "rhs": 12},
        {"coefficients": [3, 2], "relation": "<=", "rhs": 18},
    ]
    assert point_set(actual_vertices(constraints)) == {
        (0, 0), (4, 0), (4, 3), (2, 6), (0, 6)
    }


def test_mixed_ge_constraints_vertices():
    constraints = [
        {"coefficients": [1, 1], "relation": "<=", "rhs": 4},
        {"coefficients": [1, 0], "relation": ">=", "rhs": 1},
        {"coefficients": [0, 1], "relation": ">=", "rhs": 1},
    ]
    assert point_set(actual_vertices(constraints)) == {
        (1, 1), (3, 1), (1, 3)
    }
    for p in actual_vertices(constraints):
        assert point_satisfies_constraints(p, constraints)


def test_equality_feasible_set_is_a_segment():
    constraints = [
        {"coefficients": [1, 1], "relation": "=", "rhs": 4},
        {"coefficients": [1, 0], "relation": "<=", "rhs": 3},
        {"coefficients": [0, 1], "relation": "<=", "rhs": 3},
    ]
    assert point_set(actual_vertices(constraints)) == {(1, 3), (3, 1)}
    # Equality sets have zero area: use actual vertices to draw a segment.
    assert clip_region(constraints, 6, 8) == []


def test_negative_rhs_can_define_a_feasible_region():
    constraints = [
        {"coefficients": [-1, 0], "relation": "<=", "rhs": -1},
        {"coefficients": [1, 0], "relation": "<=", "rhs": 3},
        {"coefficients": [0, 1], "relation": "<=", "rhs": 2},
    ]
    assert point_set(actual_vertices(constraints)) == {
        (1, 0), (3, 0), (3, 2), (1, 2)
    }
    region = clip_region(constraints, 6, 8)
    assert polygon_area(region) > 0
    for p in region:
        assert point_satisfies_constraints(p, constraints)


def test_infeasible_mixed_constraints_have_no_vertices():
    constraints = [
        {"coefficients": [1, 0], "relation": ">=", "rhs": 3},
        {"coefficients": [1, 0], "relation": "<=", "rhs": 2},
    ]
    assert actual_vertices(constraints) == []
    assert clip_region(constraints, 6, 8) == []


def test_boundary_segment_clips_to_viewport():
    segment = boundary_segment(1, 1, 4, 6, 8)
    assert segment is not None
    points = point_set(segment)
    assert points == {(0, 4), (4, 0)}


def test_equality_ray_is_clipped_to_viewport_for_drawing():
    constraints = [
        {"coefficients": [1, 0], "relation": "=", "rhs": 1},
        {"coefficients": [1, 0], "relation": ">=", "rhs": 1},
    ]
    points = feasible_viewport_points(constraints, 6, 8)
    assert (1.0, 0.0) in point_set(points)
    assert (1.0, 8.0) in point_set(points)
    assert all(point_satisfies_constraints(p, constraints) for p in points)
    # Viewport endpoint is for drawing only, not an actual LP vertex.
    assert point_set(actual_vertices(constraints)) == {(1, 0)}


def test_degenerate_opposing_inequalities_draw_as_segment():
    constraints = [
        {"coefficients": [1, 0], "relation": ">=", "rhs": 2},
        {"coefficients": [1, 0], "relation": "<=", "rhs": 2},
    ]
    points = feasible_viewport_points(constraints, 6, 8)
    assert (2.0, 0.0) in point_set(points)
    assert (2.0, 8.0) in point_set(points)
    assert point_set(actual_vertices(constraints)) == {(2, 0)}

def test_single_point_feasible_set_draw_point():
    constraints = [
        {"coefficients": [1, 0], "relation": "=", "rhs": 2},
        {"coefficients": [0, 1], "relation": "=", "rhs": 3},
    ]
    points = feasible_viewport_points(constraints, 6, 8)
    assert point_set(points) == {(2, 3)}
