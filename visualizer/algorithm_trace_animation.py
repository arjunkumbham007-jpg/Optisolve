"""Animated view of the actual tableau trace produced by the C++ solver."""

import json
import os
import math
import textwrap
from pathlib import Path

from manim import *

ROOT = Path(__file__).resolve().parents[1]
RESULT_FILE = Path(os.environ.get("OPTISOLVE_RESULT_JSON", ROOT / "solver" / "optisolve_result.json")).expanduser().resolve()
MAX_STEPS_IN_VIDEO = 24
MAX_TABLEAU_ROWS = 8       # includes objective row
MAX_TABLEAU_COLUMNS = 9    # variables plus RHS; basis label is additional


def _fmt(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(value):
        return "—"
    if abs(value) < 1e-8:
        return "0"
    if abs(value) >= 1e5 or abs(value) < 1e-4:
        return f"{value:.3g}"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _pretty_phase(phase):
    return {
        "simplex": "STANDARD SIMPLEX",
        "phase_i": "TWO-PHASE SIMPLEX · PHASE I",
        "phase_ii": "TWO-PHASE SIMPLEX · PHASE II",
        "big_m": "BIG-M METHOD",
    }.get(phase, str(phase or "SOLVER").replace("_", " ").upper())


def _pretty_event(event):
    return {
        "phase_start": "INITIAL TABLEAU",
        "pivot": "PIVOT OPERATION",
        "phase_transition": "PHASE TRANSITION",
        "optimal": "PHASE OPTIMAL",
        "infeasible": "INFEASIBLE MODEL",
        "unbounded": "UNBOUNDED OBJECTIVE",
        "iteration_limit": "ITERATION LIMIT REACHED",
        "invalid_model": "MODEL / NUMERICAL ERROR",
    }.get(event, str(event or "STEP").replace("_", " ").upper())


def _select_steps(trace, limit=MAX_STEPS_IN_VIDEO):
    """Keep the video short while preserving starts, transitions, and endings."""
    if len(trace) <= limit:
        return list(enumerate(trace))

    mandatory = {0, len(trace) - 1}
    terminal_events = {
        "phase_start", "phase_transition", "optimal", "infeasible",
        "unbounded", "iteration_limit", "invalid_model",
    }
    for index, step in enumerate(trace):
        if step.get("event") in terminal_events:
            mandatory.add(index)

    chosen = set(sorted(mandatory)[:limit])
    remaining_slots = limit - len(chosen)
    if remaining_slots > 0:
        candidates = [i for i in range(len(trace)) if i not in chosen]
        if candidates:
            for k in range(remaining_slots):
                position = round((k + 1) * (len(candidates) - 1) / (remaining_slots + 1))
                chosen.add(candidates[position])
                if len(chosen) >= limit:
                    break

    selected = sorted(chosen)
    if len(selected) > limit:
        selected = selected[: limit - 1] + [len(trace) - 1]
    return [(index, trace[index]) for index in selected]


def _build_tableau(step):
    tableau = step.get("tableau")
    names = step.get("column_names") or []
    basis = step.get("basis") or []

    if not step.get("tableau_recorded") or not isinstance(tableau, list) or not tableau:
        return None, "This step has no recorded matrix snapshot. See the full trace on the OptiSolve page."

    row_count = len(tableau)
    col_count = max((len(row) for row in tableau if isinstance(row, list)), default=0)
    if row_count > MAX_TABLEAU_ROWS or col_count > MAX_TABLEAU_COLUMNS:
        return None, (
            f"Tableau omitted from this video for readability ({row_count} rows × "
            f"{col_count} numeric columns). The complete matrix remains available in the webpage trace."
        )

    header = ["Basis"] + list(names) + ["RHS"]
    rows = []
    for row_index, row in enumerate(tableau):
        if row_index < len(basis):
            label = basis[row_index]
        elif step.get("phase") == "phase_i":
            label = "Phase I obj"
        else:
            label = "Objective"
        rows.append([label] + [_fmt(value) for value in row])
    return [header] + rows, None


class AlgorithmTraceAnimation(Scene):
    """Render actual recorded solver states and pivot selections into an MP4."""

    def construct(self):
        if not RESULT_FILE.is_file():
            self._error_card("Solver result JSON was not found.")
            return

        try:
            with RESULT_FILE.open("r", encoding="utf-8") as handle:
                result = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._error_card(f"Could not read solver trace: {exc}")
            return

        trace = result.get("trace") or []
        selected_steps = _select_steps(trace)
        if not selected_steps:
            self._error_card("This solve did not produce any trace events.")
            return

        method = str(result.get("method", "solver")).replace("_", " ").upper()
        overall_status = str(result.get("status", "unknown")).upper()
        is_sampled = len(selected_steps) < len(trace)
        current_group = None

        for video_index, (trace_index, step) in enumerate(selected_steps):
            next_step = None
            if video_index + 1 < len(selected_steps):
                next_index, candidate_next = selected_steps[video_index + 1]
                # Only narrate a direct transition if the next original trace event
                # is also rendered. Do not imply continuity across sampled-out steps.
                if next_index == trace_index + 1:
                    next_step = candidate_next

            group = self._make_step_group(
                result=result,
                method=method,
                overall_status=overall_status,
                step=step,
                next_step=next_step,
                trace_index=trace_index,
                total_trace_steps=len(trace),
                video_index=video_index,
                video_step_count=len(selected_steps),
                is_sampled=is_sampled,
            )

            if current_group is not None:
                self.play(FadeOut(current_group), run_time=0.22)
            self.play(FadeIn(group), run_time=0.45)
            self.wait(0.75 if step.get("event") == "pivot" else 0.95)
            current_group = group

    def _make_step_group(
        self,
        result,
        method,
        overall_status,
        step,
        next_step,
        trace_index,
        total_trace_steps,
        video_index,
        video_step_count,
        is_sampled,
    ):
        elements = []
        title = Text("OPTISOLVE · ALGORITHM TRACE", font_size=25, weight=BOLD, color=BLUE_B)
        title.move_to([0, 3.58, 0])
        elements.append(title)

        counter = Text(
            f"Step {trace_index + 1} of {total_trace_steps}  ·  {method}",
            font_size=16,
            color=GREY_B,
        ).move_to([0, 3.13, 0])
        elements.append(counter)

        phase = Text(_pretty_phase(step.get("phase")), font_size=21, weight=BOLD, color=TEAL_B)
        phase.move_to([0, 2.67, 0])
        elements.append(phase)

        event = Text(_pretty_event(step.get("event")), font_size=18, color=YELLOW_B)
        event.move_to([0, 2.28, 0])
        elements.append(event)

        explanation = str(step.get("explanation") or "Solver state recorded.")
        wrapped = textwrap.wrap(explanation, width=100) or ["Solver state recorded."]
        wrapped = wrapped[:2]
        explanation_text = Paragraph(
            *wrapped,
            font_size=16,
            line_spacing=0.65,
            alignment="center",
            color=WHITE,
        )
        explanation_text.move_to([0, 1.67, 0])
        elements.append(explanation_text)

        table_data, table_note = _build_tableau(step)
        if table_data:
            table_group = self._draw_tableau(table_data, step)
            table_group.move_to([0, -0.72, 0])
            elements.append(table_group)
        else:
            note_lines = textwrap.wrap(table_note or "Tableau not shown.", width=72)[:4]
            note = Paragraph(*note_lines, font_size=18, alignment="center", color=GREY_B)
            note.move_to([0, -0.65, 0])
            elements.append(note)

        reduced_costs = step.get("reduced_costs") or []
        if (
            step.get("event") == "pivot"
            and reduced_costs
            and len(reduced_costs) <= 6
            and len(step.get("tableau") or []) <= 5
        ):
            reduced_parts = []
            for candidate in reduced_costs:
                variable = str(candidate.get("variable", "?"))
                value = _fmt(candidate.get("tableau_coefficient", 0))
                if candidate.get("selected"):
                    tag = "ENTER"
                elif candidate.get("artificial"):
                    tag = "artificial / excluded"
                elif candidate.get("eligible"):
                    tag = "eligible later"
                else:
                    tag = "not eligible"
                reduced_parts.append(f"{variable}: {value} ({tag})")
            reduced_sentence = (
                "Entering test (normalized bottom-row coefficient; Bland's rule): "
                + "  ·  ".join(reduced_parts)
            )
            reduced_lines = textwrap.wrap(reduced_sentence, width=110)[:2]
            reduced_text = Paragraph(
                *reduced_lines,
                font_size=10,
                line_spacing=0.5,
                alignment="center",
                color=BLUE_B,
            ).move_to([0, -2.00, 0])
            elements.append(reduced_text)

        ratio_tests = step.get("ratio_tests") or []
        if step.get("event") == "pivot" and ratio_tests and len(ratio_tests) <= 5:
            ratio_parts = []
            leaving = step.get("leaving_variable")
            for candidate in ratio_tests:
                basic = str(candidate.get("basic_variable", "?"))
                coeff = _fmt(candidate.get("entering_coefficient", 0))
                if not candidate.get("eligible"):
                    ratio_parts.append(f"{basic}: coeff {coeff} → ineligible")
                else:
                    ratio_text = _fmt(candidate.get("ratio", 0))
                    suffix = " ← leaves" if basic == leaving else ""
                    ratio_parts.append(f"{basic}: {ratio_text}{suffix}")
            ratio_sentence = "Minimum-ratio test: " + "  ·  ".join(ratio_parts)
            ratio_lines = textwrap.wrap(ratio_sentence, width=100)[:2]
            ratio_text = Paragraph(
                *ratio_lines,
                font_size=12,
                line_spacing=0.55,
                alignment="center",
                color=GREEN_B,
            ).move_to([0, -2.42, 0])
            elements.append(ratio_text)

        row_operations = step.get("row_operations") or []
        has_row_operation_summary = False
        if step.get("event") == "pivot" and row_operations:
            tableau = step.get("tableau") or []
            basis = step.get("basis") or []
            if len(tableau) <= 5 and len(row_operations) <= 4:
                def _row_name(index):
                    return "Objective" if index == len(basis) + 1 else f"R{index}"

                operation_parts = []
                for operation in row_operations:
                    target_index = int(operation.get("target_row", 0))
                    source_index = int(operation.get("source_row", 0))
                    factor = float(operation.get("factor", 0.0))
                    target = _row_name(target_index)
                    source = _row_name(source_index)
                    if operation.get("operation") == "divide":
                        operation_parts.append(f"{target} ← {target} / {_fmt(factor)}")
                    elif operation.get("operation") == "subtract_multiple":
                        sign = "+" if factor < 0 else "−"
                        operation_parts.append(
                            f"{target} ← {target} {sign} {_fmt(abs(factor))}·{source}"
                        )

                if operation_parts:
                    operation_sentence = "Row operations (in order): " + "  ·  ".join(operation_parts)
                    operation_lines = textwrap.wrap(operation_sentence, width=125)[:2]
                    operation_text = Paragraph(
                        *operation_lines,
                        font_size=9,
                        line_spacing=0.45,
                        alignment="center",
                        color=PURPLE_B,
                    ).move_to([0, -2.80, 0])
                    elements.append(operation_text)
                    has_row_operation_summary = True
            else:
                operation_note = Text(
                    f"{len(row_operations)} row operations recorded · full list on webpage",
                    font_size=10,
                    color=PURPLE_B,
                ).move_to([0, -2.80, 0])
                elements.append(operation_note)
                has_row_operation_summary = True

        pivot_parts = []
        if step.get("entering_variable"):
            pivot_parts.append(f"Entering: {step['entering_variable']}")
        if step.get("leaving_variable"):
            pivot_parts.append(f"Leaving: {step['leaving_variable']}")
        pivot_value = step.get("pivot_value")
        if pivot_value is not None and pivot_parts:
            pivot_parts.append(f"Pivot: {_fmt(pivot_value)}")
        if pivot_parts:
            pivot_line = Text("   ·   ".join(pivot_parts), font_size=15, color=YELLOW_B)
            pivot_line.move_to([0, -3.16 if has_row_operation_summary else -2.91, 0])
            elements.append(pivot_line)

        if is_sampled:
            footer_message = (
                f"Showing {video_step_count} selected steps from {total_trace_steps}. "
                "Open Algorithm steps on the webpage for the full trace."
            )
        else:
            footer_message = "Recorded from the C++ solver's actual tableau state."

        if trace_index == total_trace_steps - 1:
            solution = result.get("solution")
            if overall_status == "OPTIMAL" and isinstance(solution, dict):
                values = solution.get("variables") or []
                values_text = ", ".join(
                    f"x{i + 1}={_fmt(value)}" for i, value in enumerate(values[:8])
                )
                if len(values) > 8:
                    values_text += ", …"
                footer_message = (
                    f"FINAL: Z={_fmt(solution.get('objective_value'))}  ·  "
                    f"{values_text}  ·  STATUS {overall_status}"
                )
            else:
                footer_message = f"FINAL STATUS: {overall_status}"

        if step.get("event") == "pivot" and next_step and next_step.get("phase") == step.get("phase"):
            next_event = next_step.get("event")
            if next_event == "pivot":
                next_entering = next_step.get("entering_variable") or "?"
                next_leaving = next_step.get("leaving_variable") or "?"
                footer_message = f"NEXT ITERATION: {next_entering} enters · {next_leaving} leaves"
            elif next_event == "optimal" and step.get("phase") == "phase_i":
                footer_message = "NEXT STATE: Phase I optimum · feasibility check follows"
            elif next_event == "optimal" and step.get("phase") == "phase_ii":
                footer_message = "NEXT STATE: Phase II optimality check"
            elif next_event == "optimal":
                footer_message = "NEXT STATE: no eligible improving reduced cost remains"

        footer = Text(footer_message, font_size=13, color=GREY_B)
        footer.move_to([0, -3.48, 0])
        elements.append(footer)
        return VGroup(*elements)

    def _draw_tableau(self, table_data, step):
        row_count = len(table_data)
        column_count = len(table_data[0])
        cell_width = min(1.36, 13.2 / column_count)
        cell_height = 0.40 if row_count <= 7 else 0.34
        header_font = 13 if column_count >= 8 else 14
        value_font = 14 if column_count >= 8 else 15
        cells = VGroup()

        pivot_row = step.get("pivot_row")
        pivot_column = step.get("pivot_column")

        for row_index, row in enumerate(table_data):
            if len(row) < column_count:
                row = list(row) + [""] * (column_count - len(row))
            for column_index, value in enumerate(row):
                rectangle = Rectangle(
                    width=cell_width,
                    height=cell_height,
                    stroke_color=GREY_B,
                    stroke_width=0.7,
                )
                if row_index == 0:
                    rectangle.set_fill(BLUE_E, opacity=0.92)
                elif column_index == 0:
                    rectangle.set_fill(BLUE_D, opacity=0.40)
                elif row_index == row_count - 1:
                    rectangle.set_fill(GREY_E, opacity=0.48)
                else:
                    rectangle.set_fill(BLACK, opacity=0.38)

                is_pivot = (
                    step.get("event") == "pivot"
                    and pivot_row is not None
                    and pivot_column is not None
                    and row_index == int(pivot_row)
                    and column_index == int(pivot_column)
                )
                if is_pivot:
                    rectangle.set_fill(YELLOW, opacity=0.95)
                    rectangle.set_stroke(YELLOW, width=1.5)

                font_size = header_font if row_index == 0 else value_font
                cell_text = Text(str(value), font_size=font_size, weight="BOLD" if row_index == 0 or is_pivot else "NORMAL")
                if is_pivot:
                    cell_text.set_color(BLACK)
                elif row_index == 0:
                    cell_text.set_color(WHITE)
                elif column_index == 0:
                    cell_text.set_color(TEAL_A)
                else:
                    cell_text.set_color(WHITE)

                if cell_text.width > cell_width - 0.06:
                    cell_text.scale((cell_width - 0.06) / cell_text.width)
                cell_text.move_to(rectangle.get_center())
                cells.add(VGroup(rectangle, cell_text))

        # Arrange the individual cells in a grid, row-major.
        for i, cell in enumerate(cells):
            r = i // column_count
            c = i % column_count
            x = (c - (column_count - 1) / 2) * cell_width
            y = ((row_count - 1) / 2 - r) * cell_height
            cell.move_to([x, y, 0])

        return cells

    def _error_card(self, message):
        title = Text("OPTISOLVE · ALGORITHM TRACE", font_size=27, weight=BOLD)
        body = Paragraph(*textwrap.wrap(message, width=58), font_size=21, alignment="center")
        self.play(Write(title), FadeIn(body))
        self.wait(2)
