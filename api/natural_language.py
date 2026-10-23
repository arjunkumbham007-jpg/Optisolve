"""A conservative, review-first parser for formula-style LP descriptions.

This module intentionally does not guess a mathematical model from arbitrary
business prose. It accepts explicit linear expressions phrased using common
math words, extracts an editable model, and leaves solving to the existing API.
"""

from __future__ import annotations

import math
import re
from typing import Any

MAX_VARIABLES = 20
MAX_CONSTRAINTS = 100

_NUMBER = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_TERM = re.compile(
    rf"(?P<sign>[+-]?)\s*(?:(?P<coefficient>{_NUMBER})\s*(?:\*\s*)?)?"
    r"x\s*_?\s*(?P<index>\d+)\b",
    re.IGNORECASE,
)


def _normalise_words(text: str) -> str:
    value = text.replace("≤", " <= ").replace("≥", " >= ").replace("−", "-").replace("–", "-")
    replacements = [
        (r"\bgreater\s+than\s+or\s+equal\s+to\b", " >= "),
        (r"\bgreater\s+than\s+or\s+equal\b", " >= "),
        (r"\bno\s+less\s+than\b", " >= "),
        (r"\bat\s+least\b", " >= "),
        (r"\bnot\s+less\s+than\b", " >= "),
        (r"\bless\s+than\s+or\s+equal\s+to\b", " <= "),
        (r"\bless\s+than\s+or\s+equal\b", " <= "),
        (r"\bno\s+more\s+than\b", " <= "),
        (r"\bnot\s+more\s+than\b", " <= "),
        (r"\bat\s+most\b", " <= "),
        (r"\bup\s+to\b", " <= "),
        (r"\bequal\s+to\b", " = "),
        (r"\bequals\b", " = "),
        (r"\bequal\b", " = "),
        (r"\bexactly\b", " = "),
        (r"\bplus\b", " + "),
        (r"\bminus\b", " - "),
        (r"\bmultiplied\s+by\b", " * "),
        (r"\btimes\b", " * "),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    # Normalize common spoken variable spellings: "x 1" and "x_1".
    value = re.sub(r"\bx\s+(\d+)\b", r"x\1", value, flags=re.IGNORECASE)
    # Preserve line breaks because they are useful constraint delimiters.
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    return value.strip()


def _parse_linear_expression(expression: str) -> dict[int, float]:
    """Parse an explicit sum of numeric multiples of x1, x2, ... ."""
    source = expression.strip()
    if source in {"0", "+0", "-0"}:
        return {}
    if not source:
        raise ValueError("Expected a linear expression such as 3x1 + 2x2.")

    coefficients: dict[int, float] = {}
    cursor = 0
    matches = list(_TERM.finditer(source))
    if not matches:
        raise ValueError(
            f"Could not find decision-variable terms in '{expression}'. "
            "Use explicit variables such as x1 and x2."
        )

    for match in matches:
        gap = source[cursor:match.start()]
        if re.sub(r"[\s+()-]", "", gap):
            raise ValueError(
                f"Unsupported expression near '{gap.strip()}'. "
                "Use a linear sum such as 3x1 - 2x2."
            )
        sign = -1.0 if match.group("sign") == "-" else 1.0
        coefficient = float(match.group("coefficient") or 1.0) * sign
        index = int(match.group("index"))
        if index < 1 or index > MAX_VARIABLES:
            raise ValueError(f"Variable indexes must be between 1 and {MAX_VARIABLES}.")
        coefficients[index] = coefficients.get(index, 0.0) + coefficient
        cursor = match.end()

    tail = source[cursor:]
    if re.sub(r"[\s+()-]", "", tail):
        raise ValueError(
            f"Unsupported expression ending '{tail.strip()}'. "
            "Only linear expressions are supported."
        )

    for value in coefficients.values():
        if not math.isfinite(value):
            raise ValueError("Expression coefficients must be finite numbers.")
    return coefficients


def _parse_rhs(value: str) -> float:
    text = value.strip().replace(",", "")
    text = re.sub(r"^(?:is|of)\s+", "", text, flags=re.IGNORECASE)
    if not re.fullmatch(rf"[+-]?{_NUMBER}", text):
        raise ValueError(
            f"Could not parse right-hand side '{value.strip()}'. "
            "Use a numeric value such as 4, -2, or 3.5."
        )
    result = float(text)
    if not math.isfinite(result):
        raise ValueError("Right-hand-side values must be finite numbers.")
    return result


def _split_constraints(text: str) -> list[str]:
    # A constraint can be on its own line, separated by semicolon/comma, or
    # joined by the word "and". The parser expects one relation per row.
    pieces = re.split(r"[\n;]+|\s+and\s+", text, flags=re.IGNORECASE)
    result: list[str] = []
    for piece in pieces:
        piece = piece.strip().strip(" ,.")
        # Accept explicit numbering like "Constraint 2: x1 + x2 <= 6".
        piece = re.sub(r"^constraint\s+\d+\s*:\s*", "", piece, flags=re.IGNORECASE)
        if piece:
            result.append(piece)

    # Expand the common domain-bound shorthand "x1, x2 >= 0" into separate
    # explicit bounds. These are later recognized by /solve as built-in bounds.
    expanded_bounds: list[str] = []
    for piece in result:
        grouped = re.fullmatch(
            r"((?:x\s*_?\s*\d+\s*,\s*)+x\s*_?\s*\d+)\s*>=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
            piece,
            flags=re.IGNORECASE,
        )
        if grouped and float(grouped.group(2)) == 0.0:
            indexes = re.findall(r"x\s*_?\s*(\d+)", grouped.group(1), flags=re.IGNORECASE)
            expanded_bounds.extend(f"x{index} >= 0" for index in indexes)
        else:
            expanded_bounds.append(piece)

    # Handle comma-separated constraint rows after line splitting as well.
    expanded: list[str] = []
    for piece in expanded_bounds:
        subpieces = re.split(r"\s*,\s*(?=[+-]?\s*(?:\d|x)\b)", piece, flags=re.IGNORECASE)
        expanded.extend(part.strip().strip(" ,.") for part in subpieces if part.strip(" ,.\t"))
    return expanded


def parse_natural_language_problem(text: str) -> dict[str, Any]:
    """Extract a linear programming model from formula-style plain language.

    Example accepted input:
        Maximize Z = 3x1 plus 2x2 subject to
        x1 plus x2 at most 4
        x1 at least 1
        x2 at least 1

    The caller must show the extracted model to the user for review before
    submitting it to the numerical solver.
    """
    if not isinstance(text, str) or len(text.strip()) < 8:
        raise ValueError("Enter a complete problem with an objective and constraints.")
    if len(text) > 10000:
        raise ValueError("Description is too long; keep it under 10,000 characters.")

    value = _normalise_words(text)
    # Require a visible transition between objective and constraints to avoid
    # guessing which relations belong to the objective.
    marker = re.search(r"\b(?:subject\s+to|such\s+that|s\.?t\.?)\b\s*:?[\s]*", value, flags=re.IGNORECASE)
    if not marker:
        raise ValueError(
            "Add 'subject to' before the constraints, for example: "
            "'Maximize Z = 3x1 + 2x2 subject to x1 + x2 <= 4'."
        )

    objective_text = value[:marker.start()].strip().strip(" ,:.")
    constraints_text = value[marker.end():].strip()

    sense_match = re.search(r"\b(maximize|maximise|minimize|minimise|max|min)\b", objective_text, re.IGNORECASE)
    if not sense_match:
        raise ValueError("Start the objective with 'maximize' or 'minimize'.")
    sense_word = sense_match.group(1).lower()
    sense = "min" if sense_word.startswith("min") else "max"
    objective_expression = objective_text[sense_match.end():].strip().strip(" ,:.")

    # Allow labels like "Z =", "profit =", or "cost =" before the expression.
    objective_expression = re.sub(
        r"^(?:(?:z|profit|cost|objective)\s*=\s*)", "", objective_expression,
        flags=re.IGNORECASE,
    ).strip()
    objective_terms = _parse_linear_expression(objective_expression)

    constraint_phrases = _split_constraints(constraints_text)
    if not constraint_phrases:
        raise ValueError("Add at least one constraint after 'subject to'.")

    parsed_constraints: list[dict[str, Any]] = []
    max_index = max(objective_terms.keys(), default=0)
    for row_number, phrase in enumerate(constraint_phrases, start=1):
        relation_matches = list(re.finditer(r"<=|>=|=", phrase))
        if len(relation_matches) != 1:
            raise ValueError(
                f"Constraint {row_number} must contain exactly one relation (<=, >=, or =): '{phrase}'."
            )
        relation_match = relation_matches[0]
        lhs = phrase[:relation_match.start()].strip()
        rhs_text = phrase[relation_match.end():].strip()
        relation = relation_match.group(0)
        terms = _parse_linear_expression(lhs)
        rhs = _parse_rhs(rhs_text)
        max_index = max(max_index, max(terms.keys(), default=0))
        parsed_constraints.append({"terms": terms, "relation": relation, "rhs": rhs})

    if max_index < 1:
        raise ValueError("Could not infer any decision variables. Use x1, x2, and so on.")
    if max_index > MAX_VARIABLES:
        raise ValueError(f"This website supports at most {MAX_VARIABLES} decision variables.")
    if len(parsed_constraints) > MAX_CONSTRAINTS:
        raise ValueError(f"This website supports at most {MAX_CONSTRAINTS} constraints.")

    objective = [float(objective_terms.get(index, 0.0)) for index in range(1, max_index + 1)]
    constraints = [
        {
            "coefficients": [float(row["terms"].get(index, 0.0)) for index in range(1, max_index + 1)],
            "relation": row["relation"],
            "rhs": float(row["rhs"]),
        }
        for row in parsed_constraints
    ]

    # Explicitly tell the UI what was inferred. This is a small, transparent
    # parser, not a general semantic model of arbitrary word problems.
    return {
        "sense": sense,
        "objective_coefficients": objective,
        "constraints": constraints,
        "variable_count": max_index,
        "constraint_count": len(constraints),
        "assumptions": [
            "Decision variables are interpreted as x1, x2, ... and are nonnegative by default.",
            "Only explicit linear equations/inequalities are extracted; arbitrary business prose is not inferred reliably.",
            "Review every coefficient, relation, and right-hand side before solving.",
        ],
    }
