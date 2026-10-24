"""Pure-Python geometry helpers for two-variable LP visualization.

This module intentionally has no Manim dependency so geometry can be tested
independently of video rendering.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]
ConstraintLike = dict
EPS = 1e-8


def _lhs(constraint: ConstraintLike, point: Point) -> float:
    a, b = map(float, constraint["coefficients"])
    return a * point[0] + b * point[1]


def point_satisfies_constraints(
    point: Point,
    constraints: Sequence[ConstraintLike],
    eps: float = EPS,
) -> bool:
    x, y = point
    if x < -eps or y < -eps:
        return False
    for constraint in constraints:
        lhs = _lhs(constraint, point)
        rhs = float(constraint["rhs"])
        relation = constraint.get("relation", "<=")
        tol = eps * max(1.0, abs(lhs), abs(rhs))
        if relation == "<=" and lhs > rhs + tol:
            return False
        if relation == ">=" and lhs < rhs - tol:
            return False
        if relation == "=" and abs(lhs - rhs) > tol:
            return False
        if relation not in {"<=", ">=", "="}:
            raise ValueError(f"Unsupported relation: {relation!r}")
    return True


def _intersection(
    line1: tuple[float, float, float],
    line2: tuple[float, float, float],
    eps: float = EPS,
) -> Point | None:
    a1, b1, r1 = line1
    a2, b2, r2 = line2
    det = a1 * b2 - a2 * b1
    scale = max(1.0, abs(a1 * b2), abs(a2 * b1))
    if abs(det) <= eps * scale:
        return None
    return ((r1 * b2 - b1 * r2) / det, (a1 * r2 - r1 * a2) / det)


def actual_vertices(
    constraints: Sequence[ConstraintLike],
    eps: float = EPS,
) -> list[Point]:
    """Return feasible intersections of actual LP boundaries in x,y >= 0.

    The viewport rectangle is deliberately absent: its edges are not LP
    vertices and must never appear in the corner-point evaluation table.
    """
    lines: list[tuple[float, float, float]] = [
        (1.0, 0.0, 0.0),  # x = 0
        (0.0, 1.0, 0.0),  # y = 0
    ]
    for constraint in constraints:
        a, b = map(float, constraint["coefficients"])
        rhs = float(constraint["rhs"])
        if abs(a) > eps or abs(b) > eps:
            lines.append((a, b, rhs))

    points: list[Point] = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            point = _intersection(lines[i], lines[j], eps)
            if point is None:
                continue
            x, y = point
            if x < -eps or y < -eps:
                continue
            point = (0.0 if abs(x) <= eps else x, 0.0 if abs(y) <= eps else y)
            if not point_satisfies_constraints(point, constraints, eps):
                continue
            if not any(math.dist(point, old) <= 10 * eps for old in points):
                points.append(point)

    if points:
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        points.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return points


def _clip_polygon(
    polygon: Sequence[Point],
    a: float,
    b: float,
    rhs: float,
    eps: float = EPS,
) -> list[Point]:
    """Clip polygon against a*x + b*y <= rhs."""
    if not polygon:
        return []

    out: list[Point] = []
    prev = polygon[-1]
    prev_val = a * prev[0] + b * prev[1] - rhs
    prev_in = prev_val <= eps

    for curr in polygon:
        curr_val = a * curr[0] + b * curr[1] - rhs
        curr_in = curr_val <= eps

        if curr_in != prev_in:
            denominator = prev_val - curr_val
            if abs(denominator) > eps:
                t = prev_val / denominator
                cross = (
                    prev[0] + t * (curr[0] - prev[0]),
                    prev[1] + t * (curr[1] - prev[1]),
                )
                out.append(cross)
        if curr_in:
            out.append(curr)

        prev, prev_val, prev_in = curr, curr_val, curr_in

    cleaned: list[Point] = []
    for p in out:
        if not cleaned or math.dist(p, cleaned[-1]) > 10 * eps:
            cleaned.append(p)
    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) <= 10 * eps:
        cleaned.pop()
    return cleaned


def clip_region(
    constraints: Sequence[ConstraintLike],
    x_max: float,
    y_max: float,
    eps: float = EPS,
) -> list[Point]:
    """Return feasible portion of the first-quadrant viewport.

    Equality-constrained feasible sets can be a line or a point rather than a
    polygon. For those cases use actual_vertices() instead of a filled region.
    """
    if any(c.get("relation", "<=") == "=" for c in constraints):
        return []

    polygon: list[Point] = [
        (0.0, 0.0),
        (float(x_max), 0.0),
        (float(x_max), float(y_max)),
        (0.0, float(y_max)),
    ]
    for constraint in constraints:
        a, b = map(float, constraint["coefficients"])
        rhs = float(constraint["rhs"])
        relation = constraint.get("relation", "<=")
        if relation == "<=":
            polygon = _clip_polygon(polygon, a, b, rhs, eps)
        elif relation == ">=":
            polygon = _clip_polygon(polygon, -a, -b, -rhs, eps)
        elif relation == "=":
            return []
        else:
            raise ValueError(f"Unsupported relation: {relation!r}")
        if not polygon:
            return []

    # Normalize order and remove zero-area duplications.
    unique: list[Point] = []
    for point in polygon:
        if not any(math.dist(point, old) <= 10 * eps for old in unique):
            unique.append(point)
    if len(unique) >= 3:
        cx = sum(p[0] for p in unique) / len(unique)
        cy = sum(p[1] for p in unique) / len(unique)
        unique.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return unique



def feasible_viewport_points(
    constraints: Sequence[ConstraintLike],
    x_max: float,
    y_max: float,
    eps: float = EPS,
) -> list[Point]:
    """Return feasible intersections inside the current plotting viewport.

    Unlike actual_vertices(), this intentionally includes viewport-edge points.
    Use it only to draw a clipped zero-area feasible set (a segment, ray, or
    single point); never use these points as LP corner evaluations.
    """
    x_max = float(x_max)
    y_max = float(y_max)
    if not (math.isfinite(x_max) and math.isfinite(y_max)) or x_max <= 0 or y_max <= 0:
        raise ValueError("Viewport limits must be finite and positive.")

    lines: list[tuple[float, float, float]] = [
        (1.0, 0.0, 0.0),       # x = 0
        (1.0, 0.0, x_max),     # x = x_max
        (0.0, 1.0, 0.0),       # y = 0
        (0.0, 1.0, y_max),     # y = y_max
    ]
    for constraint in constraints:
        a, b = map(float, constraint["coefficients"])
        rhs = float(constraint["rhs"])
        if abs(a) > eps or abs(b) > eps:
            lines.append((a, b, rhs))

    points: list[Point] = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            point = _intersection(lines[i], lines[j], eps)
            if point is None:
                continue
            x, y = point
            tol_x = eps * max(1.0, x_max)
            tol_y = eps * max(1.0, y_max)
            if x < -tol_x or y < -tol_y or x > x_max + tol_x or y > y_max + tol_y:
                continue
            x = min(x_max, max(0.0, x))
            y = min(y_max, max(0.0, y))
            candidate = (x, y)
            if not point_satisfies_constraints(candidate, constraints, eps):
                continue
            if not any(math.dist(candidate, old) <= 10 * eps for old in points):
                points.append(candidate)

    if points:
        cx = sum(point[0] for point in points) / len(points)
        cy = sum(point[1] for point in points) / len(points)
        points.sort(key=lambda point: math.atan2(point[1] - cy, point[0] - cx))
    return points

def boundary_segment(
    a: float,
    b: float,
    rhs: float,
    x_max: float,
    y_max: float,
    eps: float = EPS,
) -> tuple[Point, Point] | None:
    """Find a visible viewport segment for a*x + b*y = rhs."""
    if abs(a) <= eps and abs(b) <= eps:
        return None
    candidates: list[Point] = []

    if abs(b) > eps:
        for x in (0.0, float(x_max)):
            y = (rhs - a * x) / b
            if -eps <= y <= y_max + eps:
                candidates.append((x, min(float(y_max), max(0.0, y))))
    if abs(a) > eps:
        for y in (0.0, float(y_max)):
            x = (rhs - b * y) / a
            if -eps <= x <= x_max + eps:
                candidates.append((min(float(x_max), max(0.0, x)), y))

    unique: list[Point] = []
    for point in candidates:
        if not any(math.dist(point, old) <= 10 * eps for old in unique):
            unique.append(point)
    if len(unique) < 2:
        return None
    best = max(
        ((p, q) for i, p in enumerate(unique) for q in unique[i + 1:]),
        key=lambda pair: math.dist(pair[0], pair[1]),
    )
    if math.dist(best[0], best[1]) <= eps:
        return None
    return best


def polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )) / 2.0
