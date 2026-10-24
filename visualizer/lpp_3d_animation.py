"""3D visualization of three-variable linear programs for OptiSolve.

For bounded feasible sets, shade the actual feasible faces computed from
constraint-plane intersections. For unbounded sets, show clipped constraint
planes and feasible corner points without implying the displayed box is a
real constraint. The C++ solver's optimal solution remains authoritative.
"""
from __future__ import annotations

import itertools
import json
import math
import os
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from manim import *

ROOT = Path(__file__).resolve().parents[1]
JSON_FILE = Path(os.environ.get("OPTISOLVE_RESULT_JSON", ROOT / "solver" / "optisolve_result.json")).expanduser().resolve()
EPS = 1e-7


def _constraint_parts(constraint: dict[str, Any]) -> tuple[np.ndarray, float, str]:
    coefficients = np.asarray(constraint.get("coefficients", []), dtype=float)
    if coefficients.shape != (3,):
        raise ValueError("Each 3D constraint must have exactly three coefficients.")
    relation = constraint.get("relation")
    if relation not in {"<=", ">=", "="}:
        raise ValueError(f"Unsupported relation in 3D constraint: {relation!r}.")
    rhs = float(constraint["rhs"])
    if not np.all(np.isfinite(coefficients)) or not math.isfinite(rhs):
        raise ValueError("3D constraint values must be finite.")
    return coefficients, rhs, relation


def _feasible(point: Sequence[float], constraints: Sequence[dict[str, Any]], eps: float = EPS) -> bool:
    p = np.asarray(point, dtype=float)
    if p.shape != (3,) or not np.all(np.isfinite(p)) or np.any(p < -eps):
        return False
    for constraint in constraints:
        a, rhs, relation = _constraint_parts(constraint)
        lhs = float(np.dot(a, p))
        tol = eps * max(1.0, abs(rhs), float(np.linalg.norm(a) * np.linalg.norm(p)))
        if relation == "<=" and lhs > rhs + tol:
            return False
        if relation == ">=" and lhs < rhs - tol:
            return False
        if relation == "=" and abs(lhs - rhs) > tol:
            return False
    return True


def feasible_vertices_3d(constraints: Sequence[dict[str, Any]], eps: float = EPS) -> list[tuple[float, float, float]]:
    """Enumerate feasible vertices from triples of constraint/domain planes."""
    planes: list[tuple[np.ndarray, float]] = []
    for constraint in constraints:
        a, rhs, _ = _constraint_parts(constraint)
        if np.linalg.norm(a) > eps:
            planes.append((a, rhs))
    planes.extend([
        (np.array([1.0, 0.0, 0.0]), 0.0),
        (np.array([0.0, 1.0, 0.0]), 0.0),
        (np.array([0.0, 0.0, 1.0]), 0.0),
    ])

    vertices: list[np.ndarray] = []
    for triple in itertools.combinations(planes, 3):
        matrix = np.vstack([item[0] for item in triple])
        rhs = np.asarray([item[1] for item in triple], dtype=float)
        # Normalize each equation to make determinant checks less sensitive to scale.
        norms = np.linalg.norm(matrix, axis=1)
        if np.any(norms <= eps):
            continue
        matrix = matrix / norms[:, None]
        rhs = rhs / norms
        if abs(float(np.linalg.det(matrix))) <= 1e-10:
            continue
        try:
            candidate = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError:
            continue
        if not _feasible(candidate, constraints, eps):
            continue
        if not any(np.linalg.norm(candidate - existing) <= 1e-6 * max(1.0, np.linalg.norm(candidate)) for existing in vertices):
            vertices.append(candidate)

    vertices.sort(key=lambda p: (round(float(p[0]), 8), round(float(p[1]), 8), round(float(p[2]), 8)))
    return [tuple(float(v) for v in point) for point in vertices]


def is_bounded_3d(constraints: Sequence[dict[str, Any]], eps: float = EPS) -> bool:
    """Test for feasible nonzero recession directions in the nonnegative orthant.

    In three dimensions, every extreme ray of the pointed recession cone is the
    intersection of at least two independent homogeneous boundary planes.
    Enumerating their cross-products detects whether any feasible ray remains.
    """
    normals: list[np.ndarray] = [
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    ]
    for constraint in constraints:
        a, _, _ = _constraint_parts(constraint)
        if np.linalg.norm(a) > eps:
            normals.append(a / np.linalg.norm(a))

    for first, second in itertools.combinations(normals, 2):
        direction = np.cross(first, second)
        magnitude = float(np.linalg.norm(direction))
        if magnitude <= 1e-10:
            continue
        direction /= magnitude
        for candidate in (direction, -direction):
            if np.any(candidate < -eps):
                continue
            feasible_direction = True
            for constraint in constraints:
                a, _, relation = _constraint_parts(constraint)
                value = float(np.dot(a, candidate))
                tol = eps * max(1.0, float(np.linalg.norm(a)))
                if relation == "<=" and value > tol:
                    feasible_direction = False
                    break
                if relation == ">=" and value < -tol:
                    feasible_direction = False
                    break
                if relation == "=" and abs(value) > tol:
                    feasible_direction = False
                    break
            if feasible_direction and float(np.max(candidate)) > eps:
                return False
    return True


def _planes(constraints: Sequence[dict[str, Any]]) -> list[tuple[np.ndarray, float]]:
    result: list[tuple[np.ndarray, float]] = []
    for constraint in constraints:
        a, rhs, _ = _constraint_parts(constraint)
        if np.linalg.norm(a) > EPS:
            result.append((a, rhs))
    result.extend([
        (np.array([1.0, 0.0, 0.0]), 0.0),
        (np.array([0.0, 1.0, 0.0]), 0.0),
        (np.array([0.0, 0.0, 1.0]), 0.0),
    ])
    return result


def _unique_points(points: Sequence[np.ndarray], eps: float = 1e-6) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - previous) <= eps for previous in result):
            result.append(np.asarray(point, dtype=float))
    return result


def order_coplanar_points(points: Sequence[Sequence[float]], normal: Sequence[float]) -> list[tuple[float, float, float]]:
    """Order points around their centroid so a Manim polygon is not self-crossing."""
    unique = _unique_points([np.asarray(p, dtype=float) for p in points])
    if len(unique) < 3:
        return [tuple(float(x) for x in p) for p in unique]
    n = np.asarray(normal, dtype=float)
    norm = float(np.linalg.norm(n))
    if norm <= EPS:
        return [tuple(float(x) for x in p) for p in unique]
    n /= norm
    reference = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, reference)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    center = np.mean(unique, axis=0)
    unique.sort(key=lambda p: math.atan2(float(np.dot(p - center, v)), float(np.dot(p - center, u))))
    return [tuple(float(x) for x in p) for p in unique]


def feasible_face_polygons_3d(vertices: Sequence[Sequence[float]], constraints: Sequence[dict[str, Any]]) -> list[list[tuple[float, float, float]]]:
    """Return non-degenerate boundary polygons formed by feasible vertices."""
    if len(vertices) < 3:
        return []
    vertex_arrays = [np.asarray(p, dtype=float) for p in vertices]
    faces: list[list[tuple[float, float, float]]] = []
    seen: set[tuple[tuple[float, float, float], ...]] = set()
    for normal, rhs in _planes(constraints):
        norm = float(np.linalg.norm(normal))
        active = [p for p in vertex_arrays if abs(float(np.dot(normal, p) - rhs)) <= EPS * max(1.0, abs(rhs), norm * float(np.linalg.norm(p)))]
        active = _unique_points(active)
        if len(active) < 3:
            continue
        ordered = order_coplanar_points(active, normal)
        arr = [np.asarray(p) for p in ordered]
        area_measure = 0.0
        for i in range(1, len(arr) - 1):
            area_measure = max(area_measure, float(np.linalg.norm(np.cross(arr[i] - arr[0], arr[i + 1] - arr[0]))))
        if area_measure <= 1e-7:
            continue
        key = tuple(sorted(tuple(round(float(x), 6) for x in p) for p in ordered))
        if key in seen:
            continue
        seen.add(key)
        faces.append(ordered)
    return faces


def _nice_step(maximum: float) -> float:
    raw = max(float(maximum) / 4.0, 1e-8)
    exponent = math.floor(math.log10(raw))
    base = raw / (10 ** exponent)
    factor = 1 if base <= 1 else 2 if base <= 2 else 5 if base <= 5 else 10
    return factor * (10 ** exponent)


def _fmt(value: float) -> str:
    value = float(value)
    if abs(value) < 1e-9:
        return "0"
    return f"{value:.4g}"


def _linear_expression(coefficients: Sequence[float]) -> str:
    names = ("x_1", "x_2", "x_3")
    terms: list[str] = []
    for coefficient, variable in zip(coefficients, names):
        coefficient = float(coefficient)
        if abs(coefficient) < 1e-10:
            continue
        magnitude = abs(coefficient)
        prefix = "" if abs(magnitude - 1.0) < 1e-10 else _fmt(magnitude)
        term = f"{prefix}{variable}"
        if not terms:
            terms.append(("-" if coefficient < 0 else "") + term)
        else:
            terms.append((" - " if coefficient < 0 else " + ") + term)
    return "".join(terms) if terms else "0"


def _plane_box_intersections(normal: Sequence[float], rhs: float, limits: Sequence[float]) -> list[tuple[float, float, float]]:
    """Intersect a plane with the twelve edges of the displayed plotting box."""
    maximum = np.asarray(limits, dtype=float)
    corners = [np.asarray([maximum[0] if i & 1 else 0.0,
                           maximum[1] if i & 2 else 0.0,
                           maximum[2] if i & 4 else 0.0]) for i in range(8)]
    normal_array = np.asarray(normal, dtype=float)
    tol = EPS * max(1.0, abs(rhs), float(np.linalg.norm(normal_array) * np.linalg.norm(maximum)))
    points: list[np.ndarray] = []
    for i, first in enumerate(corners):
        for j in range(i + 1, len(corners)):
            second = corners[j]
            if int(np.count_nonzero(np.abs(first - second) > EPS)) != 1:
                continue
            f1 = float(np.dot(normal_array, first) - rhs)
            f2 = float(np.dot(normal_array, second) - rhs)
            if abs(f1) <= tol:
                points.append(first)
            if abs(f2) <= tol:
                points.append(second)
            if f1 * f2 < 0:
                t = f1 / (f1 - f2)
                points.append(first + t * (second - first))
    return [tuple(float(x) for x in p) for p in _unique_points(points)]


class LPP3DAnimation(ThreeDScene):
    def construct(self):
        try:
            with JSON_FILE.open("r", encoding="utf-8") as file:
                result = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            self.add(Text(f"Could not load solver result: {exc}", font_size=22, color=RED))
            self.wait(2)
            return

        model = result.get("model", {})
        solution = result.get("solution")
        coefficients = model.get("objective_coefficients", [])
        constraints = model.get("constraints", [])
        values = (solution or {}).get("variables", [])
        if str(result.get("status", "")).lower() != "optimal" or solution is None:
            self.add(Text("No optimal solution is available to visualize.", font_size=24, color=RED))
            self.wait(2)
            return
        if len(coefficients) != 3 or len(values) != 3:
            self.add(Text("The 3D visualization requires exactly three variables.", font_size=24, color=RED))
            self.wait(2)
            return
        try:
            for constraint in constraints:
                _constraint_parts(constraint)
        except (ValueError, TypeError, KeyError) as exc:
            self.add(Text(f"Unsupported 3D model: {exc}", font_size=22, color=RED))
            self.wait(2)
            return

        optimum = np.asarray([float(v.get("value", 0.0)) if isinstance(v, dict) else float(v) for v in values])
        objective_value = float(solution["objective_value"])
        vertices = feasible_vertices_3d(constraints)
        bounded = is_bounded_3d(constraints)
        vertex_arrays = [np.asarray(p, dtype=float) for p in vertices]

        limits = []
        for axis in range(3):
            samples = [max(0.0, float(optimum[axis]))]
            samples.extend(max(0.0, float(point[axis])) for point in vertex_arrays)
            upper = max(4.0, max(samples, default=0.0) * 1.25 + 0.5)
            limits.append(upper)
        x_max, y_max, z_max = limits

        # Use more of the frame while keeping the model panel readable.
        self.set_camera_orientation(phi=68 * DEGREES, theta=-48 * DEGREES, zoom=0.90)
        axes = ThreeDAxes(
            x_range=[0, x_max, _nice_step(x_max)],
            y_range=[0, y_max, _nice_step(y_max)],
            z_range=[0, z_max, _nice_step(z_max)],
            x_length=5.4,
            y_length=5.1,
            z_length=4.4,
            axis_config={"include_numbers": True, "font_size": 13, "stroke_width": 1.8},
        ).move_to(LEFT * 1.55 + DOWN * 0.25)
        axis_labels = axes.get_axis_labels(
            x_label=MathTex("x_1", font_size=20),
            y_label=MathTex("x_2", font_size=20),
            z_label=MathTex("x_3", font_size=20),
        )

        title = Text("OptiSolve | 3D Feasible Region", font_size=25, weight=BOLD).to_edge(UP, buff=0.18)
        model_heading = Text("MODEL", font_size=16, weight=BOLD).move_to([4.85, 2.65, 0])
        sense = str(model.get("sense", "maximize")).lower()
        sense_tex = r"\max" if sense.startswith("max") else r"\min"
        objective = MathTex(rf"{sense_tex}\ Z={_linear_expression(coefficients)}", color=YELLOW, font_size=19).move_to([4.85, 2.12, 0])
        palette = [BLUE, ORANGE, TEAL, PURPLE, PINK, GOLD, MAROON]
        constraint_lines = VGroup()
        for index, constraint in enumerate(constraints[:5]):
            lhs = _linear_expression(constraint["coefficients"])
            relation = {"<=": r"\leq", ">=": r"\geq", "=": "="}[constraint["relation"]]
            equation = MathTex(rf"{lhs}{relation}{_fmt(constraint['rhs'])}", font_size=14, color=palette[index % len(palette)])
            equation.move_to([4.85, 1.57 - index * 0.34, 0])
            constraint_lines.add(equation)
        more_constraints = None
        if len(constraints) > 5:
            more_constraints = Text(f"+ {len(constraints) - 5} more constraint(s)", font_size=12, color=GRAY_B).move_to([4.85, 1.57 - 5 * 0.34, 0])

        optimum_text = VGroup(
            Text(f"Optimal point: ({_fmt(optimum[0])}, {_fmt(optimum[1])}, {_fmt(optimum[2])})", font_size=14, color=GOLD),
            Text(f"Objective value: {_fmt(objective_value)}", font_size=14, color=GOLD),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.10).move_to([4.95, -1.05, 0])
        if bounded:
            geometry_note = Text("Bounded feasible set", font_size=12, color=GREEN_B).move_to([4.85, -2.10, 0])
        else:
            geometry_note = Text("Unbounded: planes are clipped to the view", font_size=11, color=ORANGE).move_to([4.85, -2.10, 0])

        self.add_fixed_in_frame_mobjects(title, model_heading, objective, constraint_lines, optimum_text, geometry_note)
        if more_constraints is not None:
            self.add_fixed_in_frame_mobjects(more_constraints)
        self.play(Create(axes), FadeIn(axis_labels), run_time=1.0)
        self.play(Write(title), Write(model_heading), Write(objective), run_time=0.45)
        if len(constraint_lines):
            self.play(LaggedStart(*[Write(item) for item in constraint_lines], lag_ratio=0.08), run_time=0.65)
        if more_constraints is not None:
            self.play(FadeIn(more_constraints), run_time=0.2)

        if bounded:
            faces = feasible_face_polygons_3d(vertices, constraints)
            face_mobjects = []
            for face in faces:
                # Identify which constraints contain this face. If an active
                # plane uses two or more variables, highlight that angled face.
                active_oblique_face = False
                for constraint in constraints:
                    coeffs = [float(value) for value in constraint["coefficients"]]
                    rhs = float(constraint["rhs"])
                    if sum(abs(value) > 1e-9 for value in coeffs) < 2:
                        continue

                    on_plane = True
                    for point in face:
                        lhs = sum(a * float(value) for a, value in zip(coeffs, point))
                        tolerance = 1e-6 * max(
                            1.0,
                            abs(rhs),
                            sum(abs(a * float(value)) for a, value in zip(coeffs, point)),
                        )
                        if abs(lhs - rhs) > tolerance:
                            on_plane = False
                            break

                    if on_plane:
                        active_oblique_face = True
                        break

                points = [axes.c2p(*point) for point in face]
                face_mobjects.append(
                    Polygon(
                        *points,
                        fill_color=ORANGE if active_oblique_face else GREEN,
                        fill_opacity=0.30 if active_oblique_face else 0.13,
                        stroke_color=GOLD if active_oblique_face else GREEN_B,
                        stroke_width=2.6 if active_oblique_face else 1.6,
                    )
                )
            if face_mobjects:
                self.play(
                    LaggedStart(*[FadeIn(face) for face in face_mobjects], lag_ratio=0.06),
                    run_time=0.9,
                )
            elif len(vertices) >= 2:
                # Lower-dimensional feasible sets may be a line segment rather than a volume.
                pairs = [(vertices[i], vertices[j]) for i in range(len(vertices)) for j in range(i + 1, len(vertices))]
                if pairs:
                    first, second = max(pairs, key=lambda pair: math.dist(pair[0], pair[1]))
                    self.play(Create(Line(axes.c2p(*first), axes.c2p(*second), color=GREEN_B, stroke_width=4)), run_time=0.5)
        else:
            # Display clipped boundary-plane patches but do not shade the plotting box as feasible.
            surface_mobjects = []
            for index, constraint in enumerate(constraints[:8]):
                a, rhs, _ = _constraint_parts(constraint)
                points = _plane_box_intersections(a, rhs, limits)
                ordered = order_coplanar_points(points, a)
                if len(ordered) >= 3:
                    surface_mobjects.append(Polygon(*[axes.c2p(*point) for point in ordered], fill_color=palette[index % len(palette)], fill_opacity=0.09, stroke_color=palette[index % len(palette)], stroke_width=1.3))
            if surface_mobjects:
                self.play(LaggedStart(*[FadeIn(surface) for surface in surface_mobjects], lag_ratio=0.05), run_time=0.8)

        if vertices:
            dots = VGroup(*[
                Dot3D(point=axes.c2p(*point), radius=0.045, color=BLUE_B)
                for point in vertices[:40]
            ])
            self.play(FadeIn(dots), run_time=0.4)
        # Highlight the solver's optimum with a halo, a visible gold core,
        # and a camera-facing annotation connected to the exact 3D point.
        optimum_point = axes.c2p(*optimum)
        optimum_halo = Sphere(
            radius=0.23,
            resolution=(10, 18),
            fill_color=GOLD,
            fill_opacity=0.22,
            stroke_color=GOLD,
            stroke_width=1.4,
        ).move_to(optimum_point)
        optimum_dot = Dot3D(
            point=optimum_point,
            radius=0.14,
            color=GOLD,
        )

        label_coordinates = optimum + np.asarray([0.50, 0.55, 0.35])
        label_anchor = axes.c2p(*label_coordinates)
        optimum_leader = Line3D(
            start=optimum_point,
            end=label_anchor,
            color=GOLD,
            thickness=0.025,
        )
        optimum_label = Text(
            "OPTIMUM",
            font_size=14,
            color=GOLD,
            weight=BOLD,
        ).move_to(label_anchor + RIGHT * 0.65 + UP * 0.12)
        optimum_label.set_opacity(0)
        self.add_fixed_orientation_mobjects(optimum_label)

        self.play(
            FadeIn(optimum_halo),
            FadeIn(optimum_dot),
            Create(optimum_leader),
            optimum_label.animate.set_opacity(1),
            Write(optimum_text),
            FadeIn(geometry_note),
            run_time=0.7,
        )
        self.begin_ambient_camera_rotation(rate=0.06)
        self.wait(2)
        self.stop_ambient_camera_rotation()
