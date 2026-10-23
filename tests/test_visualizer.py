from visualizer.lpp_animation import actual_vertices, clip_region


def point_set(points):
    return {
        (round(x, 6), round(y, 6))
        for x, y in points
    }


def test_original_problem_corner_points():
    constraints = [
        {"coefficients": [1, 0], "rhs": 4},
        {"coefficients": [0, 2], "rhs": 12},
        {"coefficients": [3, 2], "rhs": 18},
    ]

    expected = {
        (0, 0),
        (4, 0),
        (4, 3),
        (2, 6),
        (0, 6),
    }

    assert point_set(actual_vertices(constraints)) == expected


def test_second_problem_corner_points():
    constraints = [
        {"coefficients": [1, 1], "rhs": 4},
        {"coefficients": [1, 0], "rhs": 2},
        {"coefficients": [0, 1], "rhs": 3},
    ]

    expected = {
        (0, 0),
        (2, 0),
        (2, 2),
        (1, 3),
        (0, 3),
    }

    assert point_set(actual_vertices(constraints)) == expected


def test_larger_problem_corner_points():
    constraints = [
        {"coefficients": [1, 2], "rhs": 20},
        {"coefficients": [1, 0], "rhs": 10},
        {"coefficients": [0, 1], "rhs": 8},
    ]

    expected = {
        (0, 0),
        (10, 0),
        (10, 5),
        (4, 8),
        (0, 8),
    }

    assert point_set(actual_vertices(constraints)) == expected


def test_clipped_region_is_feasible():
    constraints = [
        {"coefficients": [1, 1], "rhs": 4},
        {"coefficients": [1, 0], "rhs": 2},
        {"coefficients": [0, 1], "rhs": 3},
    ]

    region = clip_region(constraints, 6, 8)

    assert len(region) >= 3

    for x, y in region:
        assert x >= -1e-7
        assert y >= -1e-7

        for constraint in constraints:
            a, b = constraint["coefficients"]
            rhs = constraint["rhs"]
            assert a * x + b * y <= rhs + 1e-7


def test_actual_vertices_exclude_viewport_corners():
    # This feasible region is unbounded upwards.
    constraints = [
        {"coefficients": [1, 0], "rhs": 2},
    ]

    expected = {
        (0, 0),
        (2, 0),
    }

    actual = actual_vertices(constraints)
    displayed = clip_region(constraints, 6, 8)

    assert point_set(actual) == expected

    # The clipped display has extra corners at the viewing-window
    # boundary. They must not appear in the actual vertex list.
    assert len(displayed) > len(actual)
