import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "visualizer" / "optisolve_graph.png"

INPUT_CANDIDATES = [
    ROOT / "solver" / "optisolve_result.json",
    ROOT / "optisolve_result.json",
]

EPS = 1e-8


def load_json():
    for path in INPUT_CANDIDATES:
        if path.is_file():
            with path.open(encoding="utf-8") as file:
                return json.load(file), path

    raise FileNotFoundError(
        "Could not find optisolve_result.json. "
        "Run the C++ solver first."
    )


def intersection(line1, line2):
    a1, b1, r1 = line1
    a2, b2, r2 = line2

    determinant = a1 * b2 - a2 * b1

    if abs(determinant) < EPS:
        return None

    x = (r1 * b2 - b1 * r2) / determinant
    y = (a1 * r2 - r1 * a2) / determinant

    if not math.isfinite(x) or not math.isfinite(y):
        return None

    return x, y


def satisfies_constraints(x, y, constraints):
    if x < -EPS or y < -EPS:
        return False

    for constraint in constraints:
        a, b = constraint["coefficients"]
        rhs = constraint["rhs"]

        tolerance = EPS * max(1.0, abs(rhs))

        if a * x + b * y > rhs + tolerance:
            return False

    return True


def find_vertices(constraints):
    # The first version assumes x1 >= 0 and x2 >= 0.
    lines = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]

    for constraint in constraints:
        a, b = constraint["coefficients"]
        lines.append((a, b, constraint["rhs"]))

    vertices = []

    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            point = intersection(lines[i], lines[j])

            if point is None:
                continue

            x, y = point

            if satisfies_constraints(x, y, constraints):
                point = (max(0.0, x), max(0.0, y))

                if not any(
                    abs(point[0] - old[0]) < 1e-6
                    and abs(point[1] - old[1]) < 1e-6
                    for old in vertices
                ):
                    vertices.append(point)

    return vertices


def axis_limit(axis, vertices, constraints, solution):
    values = [point[axis] for point in vertices]

    if solution and len(solution.get("variables", [])) == 2:
        values.append(abs(float(solution["variables"][axis])))

    largest = max(values, default=0.0)

    if largest > EPS:
        return largest * 1.2

    # Fallback for degenerate or unbounded cases.
    fallback = [1.0]

    for constraint in constraints:
        coefficient = constraint["coefficients"][axis]

        if abs(coefficient) > EPS:
            fallback.append(abs(constraint["rhs"] / coefficient))

    return max(fallback) * 1.2


def format_expression(coefficients, names):
    terms = []

    for coefficient, name in zip(coefficients, names):
        if abs(coefficient) < EPS:
            continue

        magnitude = abs(coefficient)

        if abs(magnitude - 1.0) < EPS:
            term = name
        else:
            term = f"{magnitude:g}{name}"

        if not terms:
            terms.append(
                ("-" if coefficient < 0 else "") + term
            )
        else:
            sign = " - " if coefficient < 0 else " + "
            terms.append(sign + term)

    return "".join(terms) if terms else "0"


def main():
    data, input_path = load_json()

    model = data["model"]

    names = model.get("variable_names", ["x1", "x2"])
    objective = model["objective_coefficients"]
    raw_constraints = model["constraints"]

    if len(objective) != 2:
        raise ValueError(
            "Graphing currently supports exactly two variables."
        )

    if model.get("nonnegative_variables") is not True:
        raise ValueError(
            "Graphing currently assumes nonnegative variables."
        )

    constraints = []

    for item in raw_constraints:
        coefficients = item["coefficients"]

        if len(coefficients) != 2:
            raise ValueError(
                "Every constraint must have two coefficients."
            )

        if item["relation"] != "<=":
            raise ValueError(
                "This graph version supports <= constraints only."
            )

        coefficients = [float(v) for v in coefficients]
        rhs = float(item["rhs"])

        if not all(math.isfinite(v) for v in coefficients + [rhs]):
            raise ValueError("Constraint values must be finite.")

        constraints.append({
            "coefficients": coefficients,
            "relation": item["relation"],
            "rhs": rhs,
        })

    objective = [float(v) for v in objective]

    if not all(math.isfinite(v) for v in objective):
        raise ValueError("Objective coefficients must be finite.")

    solution = data.get("solution")

    if solution is not None:
        variables = solution.get("variables", [])

        if len(variables) != 2:
            solution = None
        elif not all(math.isfinite(float(v)) for v in variables):
            raise ValueError("Solution values must be finite.")

    vertices = find_vertices(constraints)

    x_max = axis_limit(0, vertices, constraints, solution)
    y_max = axis_limit(1, vertices, constraints, solution)

    x_values = np.linspace(0, x_max, 400)
    y_values = np.linspace(0, y_max, 400)
    X, Y = np.meshgrid(x_values, y_values)

    feasible = np.ones(X.shape, dtype=bool)

    for constraint in constraints:
        a, b = constraint["coefficients"]
        rhs = constraint["rhs"]

        feasible &= (
            a * X + b * Y
            <= rhs + EPS * max(1.0, abs(rhs))
        )

    fig, ax = plt.subplots(figsize=(10, 7))

    if feasible.any():
        ax.contourf(
            X,
            Y,
            feasible.astype(float),
            levels=[0.5, 1.5],
            colors=["#8bd3a8"],
            alpha=0.35,
        )

    legend_handles = [
        Patch(
            facecolor="#8bd3a8",
            alpha=0.45,
            label="Feasible region",
        )
    ]

    for i, constraint in enumerate(constraints, start=1):
        a, b = constraint["coefficients"]
        rhs = constraint["rhs"]

        label = (
            f"C{i}: "
            f"{format_expression(constraint['coefficients'], names)}"
            f" <= {rhs:g}"
        )

        if abs(b) > EPS:
            line_y = (rhs - a * x_values) / b
            ax.plot(x_values, line_y, linewidth=1.8, label=label)
        elif abs(a) > EPS:
            line_x = rhs / a
            ax.axvline(line_x, linewidth=1.8, label=label)

    if vertices:
        vx = [point[0] for point in vertices]
        vy = [point[1] for point in vertices]

        ax.scatter(
            vx,
            vy,
            color="navy",
            s=24,
            zorder=4,
            label="Feasible-region vertices",
        )

    status = data.get("status", "unknown")

    if solution is not None and status == "optimal":
        sx, sy = map(float, solution["variables"])
        z = float(solution["objective_value"])

        if abs(objective[1]) > EPS:
            objective_y = (
                z - objective[0] * x_values
            ) / objective[1]

            ax.plot(
                x_values,
                objective_y,
                "--",
                color="purple",
                linewidth=2,
                label=f"Objective line: Z = {z:g}",
            )

        elif abs(objective[0]) > EPS:
            ax.axvline(
                z / objective[0],
                color="purple",
                linestyle="--",
                linewidth=2,
                label=f"Objective line: Z = {z:g}",
            )

        ax.scatter(
            [sx],
            [sy],
            color="red",
            marker="*",
            s=240,
            zorder=6,
            label="Optimal solution",
        )

        ax.annotate(
            f"Optimal ({sx:g}, {sy:g})\nZ = {z:g}",
            xy=(sx, sy),
            xytext=(10, 12),
            textcoords="offset points",
            fontsize=10,
            bbox={
                "boxstyle": "round,pad=0.3",
                "fc": "white",
                "alpha": 0.9,
            },
        )

    ax.set_xlim(0, x_max)
    ax.set_ylim(0, y_max)

    ax.set_xlabel(names[0])
    ax.set_ylabel(names[1])
    ax.set_title("OptiSolve — Graphical LPP Solution")

    ax.grid(True, alpha=0.25)
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1),
        fontsize=8,
    )

    fig.tight_layout()
    fig.savefig(OUTPUT_FILE, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(f"Input JSON: {input_path}")
    print(f"Solver status: {status}")

    if not feasible.any():
        print("Warning: no feasible points found in the plotted region.")

    if not vertices:
        print("Warning: no feasible-region vertices were found.")

    print(f"Graph saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
