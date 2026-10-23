"""General two-variable graphical explanation for OptiSolve.

Supports <=, >=, and = structural constraints, including negative RHS values.
The numerical answer and corner-point data come from the solver JSON output.
"""
from __future__ import annotations

import json
import os
import math
from pathlib import Path

from manim import *

from lpp_geometry import (
    actual_vertices,
    boundary_segment,
    clip_region,
    feasible_viewport_points,
    point_satisfies_constraints,
    polygon_area,
)

ROOT = Path(__file__).resolve().parents[1]
JSON_FILE = Path(os.environ.get("OPTISOLVE_RESULT_JSON", ROOT / "solver" / "optisolve_result.json")).expanduser().resolve()

BASE_X_MAX = 6.0
BASE_Y_MAX = 8.0
MAX_CONSTRAINT_LABELS = 4
MAX_VERTEX_DOTS = 45
MAX_EVALUATION_ROWS = 5


def fmt(value: float) -> str:
    value = float(value)
    if abs(value) < 1e-10:
        return "0"
    if abs(value) >= 100000 or abs(value) < 0.0001:
        mantissa, exponent = f"{value:.3e}".split("e")
        exponent = int(exponent)
        return rf"{mantissa}\times10^{{{exponent}}}"
    return f"{value:.5g}"


def num(value):
    if isinstance(value, dict):
        value = value.get("value", 0.0)
    return float(value)


def nice_step(maximum: float) -> float:
    raw = max(float(maximum) / 6.0, 1e-8)
    exponent = math.floor(math.log10(raw))
    base = raw / (10 ** exponent)
    if base <= 1:
        nice = 1
    elif base <= 2:
        nice = 2
    elif base <= 5:
        nice = 5
    else:
        nice = 10
    return nice * (10 ** exponent)


def linear_expression(coefficients, variables=("x_1", "x_2")) -> str:
    terms = []
    for coefficient, variable in zip(coefficients, variables):
        coefficient = float(coefficient)
        if abs(coefficient) < 1e-10:
            continue
        magnitude = abs(coefficient)
        coefficient_text = "" if abs(magnitude - 1.0) < 1e-10 else fmt(magnitude)
        term = f"{coefficient_text}{variable}"
        if not terms:
            terms.append(('-' if coefficient < 0 else '') + term)
        else:
            terms.append((" - " if coefficient < 0 else " + ") + term)
    return "".join(terms) if terms else "0"


def relation_tex(relation: str) -> str:
    return {"<=": r"\leq", ">=": r"\geq", "=": "="}[relation]


def farthest_pair(points):
    if len(points) < 2:
        return None
    return max(
        ((p, q) for i, p in enumerate(points) for q in points[i + 1:]),
        key=lambda pair: math.dist(pair[0], pair[1]),
    )


class LPPAnimation(Scene):
    def construct(self):
        with JSON_FILE.open("r", encoding="utf-8") as file:
            result = json.load(file)

        model = result.get("model", {})
        solution = result.get("solution")
        coefficients = model.get("objective_coefficients", [])
        constraints = model.get("constraints", [])

        if str(result.get("status", "")).lower() != "optimal" or solution is None:
            self.add(Text("No optimal solution is available to graph.", font_size=25))
            self.wait(2)
            return
        if len(coefficients) != 2:
            self.add(Text("The graph supports exactly two variables.", font_size=25))
            self.wait(2)
            return
        if any(c.get("relation") not in {"<=", ">=", "="} for c in constraints):
            self.add(Text("Unsupported constraint relation.", font_size=25, color=RED))
            self.wait(2)
            return

        c1, c2 = map(float, coefficients)
        x_opt, y_opt = [num(value) for value in solution.get("variables", [])]
        z_opt = float(solution["objective_value"])

        vertices = actual_vertices(constraints)
        if not any(math.dist((x_opt, y_opt), p) <= 1e-6 for p in vertices):
            if point_satisfies_constraints((x_opt, y_opt), constraints):
                vertices.append((x_opt, y_opt))

        scale_points = list(vertices) + [(x_opt, y_opt)]
        x_max = max(BASE_X_MAX, max(max(0.0, p[0]) for p in scale_points) * 1.22 + 0.35)
        y_max = max(BASE_Y_MAX, max(max(0.0, p[1]) for p in scale_points) * 1.22 + 0.35)
        x_step = nice_step(x_max)
        y_step = nice_step(y_max)

        title = Text("OptiSolve | Graphical LPP", font_size=28, weight=BOLD)
        title.move_to([0.0, 3.55, 0])
        self.play(Write(title), run_time=0.7)

        axes = Axes(
            x_range=[0, x_max, x_step],
            y_range=[0, y_max, y_step],
            x_length=6.15,
            y_length=4.55,
            axis_config={"include_numbers": True, "font_size": 15},
            tips=False,
        ).to_edge(LEFT, buff=0.55).shift(DOWN * 0.25)
        axis_labels = axes.get_axis_labels(
            x_label=MathTex("x_1", font_size=24),
            y_label=MathTex("x_2", font_size=24),
        )
        self.play(Create(axes), Write(axis_labels), run_time=1.0)

        display_region = clip_region(constraints, x_max, y_max)
        if len(display_region) >= 3 and polygon_area(display_region) > 1e-7:
            feasible = Polygon(
                *[axes.c2p(x, y) for x, y in display_region],
                stroke_color=GREEN,
                stroke_width=1.5,
                fill_color=GREEN,
                fill_opacity=0.26,
            )
            self.play(FadeIn(feasible), run_time=0.6)
        else:
            # Equality constraints and degenerate pairs of inequalities can
            # leave a zero-area feasible set. Clip that set to the viewport so
            # rays such as x1 = 1, x2 >= 0 are drawn as visible line segments.
            clipped_feasible_points = feasible_viewport_points(
                constraints, x_max, y_max
            )
            pair = farthest_pair(clipped_feasible_points)
            if pair and math.dist(*pair) > 1e-7:
                feasible_line = Line(
                    axes.c2p(*pair[0]), axes.c2p(*pair[1]),
                    color=GREEN, stroke_width=6,
                )
                self.play(Create(feasible_line), run_time=0.6)
            elif clipped_feasible_points:
                feasible_point = Dot(
                    axes.c2p(*clipped_feasible_points[0]),
                    color=GREEN,
                    radius=0.10,
                )
                self.play(FadeIn(feasible_point), run_time=0.35)

        # Draw every constraint boundary. Labels are intentionally capped so
        # large models remain readable instead of placing 100 equations on one slide.
        palette = [BLUE, ORANGE, TEAL, PURPLE, PINK, GOLD, MAROON]
        for index, constraint in enumerate(constraints):
            a, b = map(float, constraint["coefficients"])
            rhs = float(constraint["rhs"])
            segment = boundary_segment(a, b, rhs, x_max, y_max)
            color = palette[index % len(palette)]
            if segment is not None:
                p1, p2 = segment
                boundary = Line(
                    axes.c2p(*p1), axes.c2p(*p2),
                    color=color, stroke_width=2.7,
                )
                self.play(Create(boundary), run_time=0.18)

        model_heading = Text("MODEL", font_size=17, weight=BOLD)
        model_heading.move_to([3.75, 2.86, 0])
        sense = str(model.get("sense", "maximize")).lower()
        sense_tex = r"\max" if sense.startswith("max") else r"\min"
        objective = MathTex(
            rf"{sense_tex}\ Z={linear_expression(coefficients)}",
            color=YELLOW,
            font_size=24,
        ).move_to([3.75, 2.38, 0])
        self.play(Write(model_heading), Write(objective), run_time=0.6)

        constraint_lines = VGroup()
        shown_constraints = constraints[:MAX_CONSTRAINT_LABELS]
        for index, constraint in enumerate(shown_constraints):
            lhs = linear_expression(constraint["coefficients"])
            rhs = fmt(constraint["rhs"])
            equation = MathTex(
                rf"{lhs}{relation_tex(constraint['relation'])}{rhs}",
                font_size=19,
                color=palette[index % len(palette)],
            ).move_to([3.75, 1.82 - index * 0.36, 0])
            constraint_lines.add(equation)
        if constraint_lines:
            self.play(LaggedStart(*[Write(eq) for eq in constraint_lines], lag_ratio=0.12), run_time=0.7)

        if len(constraints) > MAX_CONSTRAINT_LABELS:
            more = Text(
                f"+ {len(constraints) - MAX_CONSTRAINT_LABELS} more constraint(s)",
                font_size=14,
                color=GRAY_B,
            ).move_to([3.75, 1.82 - MAX_CONSTRAINT_LABELS * 0.36, 0])
            self.play(FadeIn(more), run_time=0.2)

        # Mark the actual LP corner points (never artificial viewport corners).
        solution_vertex = min(
            vertices,
            key=lambda p: math.dist((x_opt, y_opt), p),
        ) if vertices else (x_opt, y_opt)
        shown_vertices = list(vertices)
        if not any(math.dist(solution_vertex, p) <= 1e-6 for p in shown_vertices):
            shown_vertices.append(solution_vertex)
        shown_vertices = shown_vertices[:MAX_VERTEX_DOTS]
        if not any(math.dist((x_opt, y_opt), p) <= 1e-6 for p in shown_vertices):
            shown_vertices[-1:] = [(x_opt, y_opt)]

        if shown_vertices:
            dots = VGroup(*[
                Dot(axes.c2p(x, y), color=BLUE_B, radius=0.045)
                for x, y in shown_vertices
            ])
            self.play(FadeIn(dots), run_time=0.35)

        # Objective contour at the optimum.
        objective_segment = boundary_segment(c1, c2, z_opt, x_max, y_max)
        if objective_segment is not None:
            objective_line = DashedVMobject(
                Line(
                    axes.c2p(*objective_segment[0]),
                    axes.c2p(*objective_segment[1]),
                    color=YELLOW,
                    stroke_width=2.5,
                ),
                num_dashes=24,
            )
            self.play(Create(objective_line), run_time=0.5)

        optimum_dot = Dot(axes.c2p(x_opt, y_opt), color=RED, radius=0.105)
        optimum_label = MathTex(
            rf"({fmt(x_opt)},{fmt(y_opt)})",
            color=RED,
            font_size=24,
        ).next_to(optimum_dot, UR, buff=0.10)
        self.play(FadeIn(optimum_dot), Write(optimum_label), run_time=0.5)

        # Order evaluations with the solver's answer first, then show a few
        # other actual feasible vertices. This avoids implying the viewport edge
        # points are LP corners.
        eval_points = list(vertices)
        if not any(math.dist((x_opt, y_opt), p) <= 1e-6 for p in eval_points):
            eval_points.append((x_opt, y_opt))
        eval_points.sort(key=lambda p: (
            0 if math.dist((x_opt, y_opt), p) <= 1e-6 else 1,
            p[0], p[1],
        ))

        corner_heading = Text("FEASIBLE CORNER CHECK", font_size=15, weight=BOLD)
        corner_heading.move_to([3.75, -0.12, 0])
        self.play(Write(corner_heading), run_time=0.3)
        eval_rows = VGroup()
        visible_evals = eval_points[:MAX_EVALUATION_ROWS]
        for index, (x, y) in enumerate(visible_evals):
            value = c1 * x + c2 * y
            row = MathTex(
                rf"({fmt(x)},{fmt(y)}):\ Z={fmt(value)}",
                font_size=18,
                color=YELLOW if math.dist((x, y), (x_opt, y_opt)) <= 1e-6 else WHITE,
            ).move_to([3.75, -0.52 - index * 0.39, 0])
            eval_rows.add(row)
        if eval_rows:
            self.play(LaggedStart(*[Write(row) for row in eval_rows], lag_ratio=0.08), run_time=0.7)

        if len(eval_points) > MAX_EVALUATION_ROWS:
            note = Text(
                f"{len(eval_points) - MAX_EVALUATION_ROWS} more vertices not listed",
                font_size=12, color=GRAY_B,
            ).move_to([3.75, -0.52 - MAX_EVALUATION_ROWS * 0.39, 0])
            self.play(FadeIn(note), run_time=0.2)

        final_result = MathTex(
            rf"\mathrm{{OPTIMUM}}:\ Z={fmt(z_opt)}",
            color=YELLOW,
            font_size=24,
        ).move_to([3.75, -3.18, 0])
        self.play(Write(final_result), run_time=0.5)
        self.wait(2)
