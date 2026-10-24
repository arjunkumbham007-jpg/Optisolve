"""High-dimensional solution profile for LPs with four or more variables.

This is deliberately not a geometric rendering of the entire feasible set.
It explains the solver's optimal variable values, objective contributions, and
constraint slack/surplus/residual in readable pages.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Sequence

from manim import *

ROOT = Path(__file__).resolve().parents[1]
JSON_FILE = Path(os.environ.get("OPTISOLVE_RESULT_JSON", ROOT / "solver" / "optisolve_result.json")).expanduser().resolve()
VARIABLES_PER_PAGE = 8
CONSTRAINTS_PER_PAGE = 6
EPS = 1e-8


def _number(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("value", 0.0)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Model values must be finite numbers.")
    return result


def _fmt(value: float) -> str:
    value = float(value)
    if abs(value) < 1e-9:
        return "0"
    return f"{value:.4g}"


def objective_contributions(objective_coefficients: Sequence[float], variables: Sequence[float]) -> list[float]:
    """Return c_i*x_i after checking that both vectors align."""
    if len(objective_coefficients) != len(variables):
        raise ValueError("Objective coefficients and variable values must have equal length.")
    result = []
    for coefficient, value in zip(objective_coefficients, variables):
        contribution = _number(coefficient) * _number(value)
        if not math.isfinite(contribution):
            raise ValueError("Objective contribution is not finite.")
        result.append(contribution)
    return result


def constraint_diagnostics(constraints: Sequence[dict[str, Any]], variables: Sequence[float]) -> list[dict[str, Any]]:
    """Calculate LHS plus meaningful slack, surplus, residual, and utilization."""
    output: list[dict[str, Any]] = []
    values = [_number(value) for value in variables]
    for index, constraint in enumerate(constraints, start=1):
        coefficients = constraint.get("coefficients")
        if not isinstance(coefficients, list) or len(coefficients) != len(values):
            raise ValueError(f"Constraint {index} must have exactly {len(values)} coefficients.")
        relation = constraint.get("relation")
        if relation not in {"<=", ">=", "="}:
            raise ValueError(f"Constraint {index} has an unsupported relation.")
        coeffs = [_number(value) for value in coefficients]
        rhs = _number(constraint.get("rhs"))
        lhs = sum(a * x for a, x in zip(coeffs, values))
        if not math.isfinite(lhs):
            raise ValueError(f"Constraint {index} left-hand side is not finite.")
        tolerance = EPS * max(1.0, abs(lhs), abs(rhs), sum(abs(a * x) for a, x in zip(coeffs, values)))
        utilization = None
        if relation == "<=":
            balance_label, balance = "Slack", rhs - lhs
            if rhs > EPS and lhs >= -EPS:
                utilization = 100.0 * lhs / rhs
            satisfied = balance >= -tolerance
        elif relation == ">=":
            balance_label, balance = "Surplus", lhs - rhs
            satisfied = balance >= -tolerance
        else:
            balance_label, balance = "Residual", lhs - rhs
            satisfied = abs(balance) <= tolerance
        output.append({
            "index": index,
            "coefficients": coeffs,
            "lhs": lhs,
            "relation": relation,
            "rhs": rhs,
            "balance_label": balance_label,
            "balance": balance,
            "utilization_percent": utilization,
            "satisfied": satisfied,
        })
    return output


def _expression(coefficients: Sequence[float], variables: Sequence[str] | None = None) -> str:
    if variables is None:
        variables = [f"x{i + 1}" for i in range(len(coefficients))]
    terms: list[str] = []
    for raw, variable in zip(coefficients, variables):
        coefficient = float(raw)
        if abs(coefficient) < EPS:
            continue
        magnitude = abs(coefficient)
        coeff_text = "" if abs(magnitude - 1.0) < EPS else _fmt(magnitude)
        term = f"{coeff_text}{variable}"
        if not terms:
            terms.append(("-" if coefficient < 0 else "") + term)
        else:
            terms.append((" - " if coefficient < 0 else " + ") + term)
    return "".join(terms) if terms else "0"


def _relation(relation: str) -> str:
    return {"<=": "<=", ">=": ">=", "=": "="}[relation]


class LPPHighDimAnimation(Scene):
    """Paged, text-and-bar view for high-dimensional LP solution diagnostics."""

    def construct(self):
        try:
            with JSON_FILE.open("r", encoding="utf-8") as file:
                result = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            self.add(Text(f"Could not load solver result: {exc}", font_size=20, color=RED))
            self.wait(2)
            return

        model = result.get("model", {})
        solution = result.get("solution")
        objective = model.get("objective_coefficients", [])
        constraints = model.get("constraints", [])
        raw_values = (solution or {}).get("variables", [])
        if str(result.get("status", "")).lower() != "optimal" or solution is None:
            self.add(Text("No optimal solution is available to summarize.", font_size=22, color=RED))
            self.wait(2)
            return
        try:
            values = [_number(value) for value in raw_values]
            objective_values = [_number(value) for value in objective]
            if len(values) < 4 or len(values) != len(objective_values):
                raise ValueError("High-dimensional profile requires 4 or more matching variables.")
            contributions = objective_contributions(objective_values, values)
            diagnostics = constraint_diagnostics(constraints, values)
            objective_value = _number(solution["objective_value"])
        except (ValueError, TypeError, KeyError) as exc:
            self.add(Text(f"Cannot summarize model: {exc}", font_size=20, color=RED))
            self.wait(2)
            return

        title = Text("OptiSolve | High-Dimensional Analysis", font_size=25, weight=BOLD)
        title.to_edge(UP, buff=0.22)
        total = Text(f"Optimal objective value: {_fmt(objective_value)}", font_size=17, color=YELLOW)
        total.next_to(title, DOWN, buff=0.16)
        self.play(Write(title), FadeIn(total), run_time=0.7)

        self._show_variable_pages(values, objective_values, contributions)
        self._show_constraint_pages(diagnostics)

        ending = VGroup(
            Text("Numerical solution and constraint checks", font_size=23, weight=BOLD, color=GREEN_B),
            Text(f"{len(values)} variables  |  {len(diagnostics)} constraints", font_size=18),
            Text("This is a solution profile, not a geometric image of the full feasible region.", font_size=14, color=GRAY_B),
        ).arrange(DOWN, buff=0.22).move_to(ORIGIN)
        self.play(FadeIn(ending), run_time=0.5)
        self.wait(1.2)

    def _show_variable_pages(self, values: list[float], objective: list[float], contributions: list[float]) -> None:
        max_abs = max((abs(value) for value in values), default=0.0) or 1.0
        page_count = math.ceil(len(values) / VARIABLES_PER_PAGE)
        for page_index in range(page_count):
            start = page_index * VARIABLES_PER_PAGE
            end = min(len(values), start + VARIABLES_PER_PAGE)
            header = Text(
                f"Decision-variable profile ({start + 1}-{end} of {len(values)})",
                font_size=21,
                weight=BOLD,
                color=BLUE_B,
            ).move_to([0, 2.45, 0])
            column_headers = VGroup(
                Text("VARIABLE", font_size=11, color=GRAY_B).move_to([-5.65, 1.97, 0]),
                Text("VALUE (relative bar)", font_size=11, color=GRAY_B).move_to([-3.35, 1.97, 0]),
                Text("c_i x_i CONTRIBUTION", font_size=11, color=GRAY_B).move_to([2.8, 1.97, 0]),
            )
            rows = VGroup()
            for local_index, index in enumerate(range(start, end)):
                y = 1.53 - local_index * 0.45
                name = Text(f"x{index + 1}", font_size=15, color=BLUE_B).move_to([-5.65, y, 0])
                track = Line([-4.8, y, 0], [-2.4, y, 0], color=GRAY_D, stroke_width=5)
                width = 2.4 * abs(values[index]) / max_abs
                if width > 1e-4:
                    bar = Line(
                        [-4.8, y, 0], [-4.8 + width, y, 0],
                        color=BLUE_C if values[index] >= 0 else ORANGE,
                        stroke_width=8,
                    )
                else:
                    bar = Dot([-4.8, y, 0], radius=0.035, color=BLUE_C)
                value_text = Text(_fmt(values[index]), font_size=14).move_to([-1.75, y, 0])
                contribution_text = Text(_fmt(contributions[index]), font_size=14, color=YELLOW).move_to([2.8, y, 0])
                rows.add(VGroup(name, track, bar, value_text, contribution_text))
            page_note = Text(
                f"Objective: {_fmt(sum(contributions))} total  |  bars normalized to largest |x_i|  |  page {page_index + 1}/{page_count}",
                font_size=11,
                color=GRAY_B,
            ).move_to([0, -2.72, 0])
            page = VGroup(header, column_headers, rows, page_note)
            self.play(FadeIn(page), run_time=0.35)
            self.wait(0.75)
            self.play(FadeOut(page), run_time=0.25)

    def _show_constraint_pages(self, diagnostics: list[dict[str, Any]]) -> None:
        if not diagnostics:
            note = Text("No structural constraints to summarize.", font_size=20, color=ORANGE)
            self.play(FadeIn(note), run_time=0.3)
            self.wait(0.7)
            self.play(FadeOut(note), run_time=0.25)
            return
        page_count = math.ceil(len(diagnostics) / CONSTRAINTS_PER_PAGE)
        relation_symbol = {"<=": "<=", ">=": ">=", "=": "="}
        for page_index in range(page_count):
            start = page_index * CONSTRAINTS_PER_PAGE
            page_rows = diagnostics[start:start + CONSTRAINTS_PER_PAGE]
            end = start + len(page_rows)
            header = Text(
                f"Constraint utilization and slack ({start + 1}-{end} of {len(diagnostics)})",
                font_size=21,
                weight=BOLD,
                color=TEAL_A,
            ).move_to([0, 2.55, 0])
            rows = VGroup()
            for local_index, item in enumerate(page_rows):
                y = 1.83 - local_index * 0.68
                equation = Text(
                    f"C{item['index']}: {_expression(item['coefficients'])} {relation_symbol[item['relation']]} {_fmt(item['rhs'])}",
                    font_size=13,
                )
                # Only shrink long equations; never enlarge short ones.
                if equation.width > 11.6:
                    equation.scale_to_fit_width(11.6)
                equation.move_to([0, y, 0])
                status = "SATISFIED" if item["satisfied"] else "VIOLATED"
                detail_parts = [f"LHS = {_fmt(item['lhs'])}", f"{item['balance_label']} = {_fmt(item['balance'])}"]
                if item["utilization_percent"] is not None:
                    detail_parts.append(f"utilization = {_fmt(item['utilization_percent'])}%")
                detail_parts.append(status)
                detail_color = GREEN_B if item["satisfied"] else RED
                detail = Text("  |  ".join(detail_parts), font_size=11, color=detail_color)
                # Keep diagnostic text at its intended readable font size.
                if detail.width > 11.6:
                    detail.scale_to_fit_width(11.6)
                detail.move_to([0, y - 0.24, 0])
                rows.add(VGroup(equation, detail))
            note = Text(
                "<=: slack; >=: surplus; =: signed residual. Utilization is shown only for nonnegative LHS with positive RHS.",
                font_size=10,
                color=GRAY_B,
            )
            if note.width > 11.8:
                note.scale_to_fit_width(11.8)
            note.move_to([0, -2.72, 0])
            page_counter = Text(f"Page {page_index + 1}/{page_count}", font_size=10, color=GRAY_B).move_to([5.8, -3.25, 0])
            page = VGroup(header, rows, note, page_counter)
            self.play(FadeIn(page), run_time=0.35)
            self.wait(0.8)
            self.play(FadeOut(page), run_time=0.25)
