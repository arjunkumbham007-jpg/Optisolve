#include "simplex.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <utility>

namespace {
constexpr double EPS = 1e-9;
constexpr double FEASIBILITY_EPS = 1e-7;
// Trace snapshots are bounded so large models cannot produce unbounded JSON.
constexpr std::size_t MAX_TRACE_EVENTS = 100;
constexpr std::size_t MAX_TRACE_TABLEAU_CELLS = 50000;

struct NormalizedConstraint {
    std::vector<double> coefficients;
    std::string relation;
    double rhs = 0.0;
};

struct TableauState {
    std::vector<std::vector<double>> tableau;
    std::vector<int> basis;
    std::vector<bool> artificial;
    std::vector<std::string> columnNames;
    std::size_t traceTableauCells = 0;
    int originalVariables = 0;
    int totalVariables = 0;
    int rhsColumn = 0;
};

bool validateModel(const LPP& model, int maxIterations, std::string& error) {
    if (model.objective.empty() || model.constraints.empty()) {
        error = "The model must contain at least one variable and one constraint.";
        return false;
    }
    if (maxIterations < 0) {
        error = "The iteration limit cannot be negative.";
        return false;
    }

    for (double coefficient : model.objective) {
        if (!std::isfinite(coefficient)) {
            error = "Non-finite objective coefficient.";
            return false;
        }
    }

    const std::size_t n = model.objective.size();
    for (const auto& constraint : model.constraints) {
        if (constraint.coefficients.size() != n) {
            error = "Constraint dimension mismatch.";
            return false;
        }
        if (constraint.relation != "<=" && constraint.relation != ">=" &&
            constraint.relation != "=") {
            error = "Invalid constraint relation; use <=, >=, or =.";
            return false;
        }
        if (!std::isfinite(constraint.rhs)) {
            error = "Non-finite right-hand side.";
            return false;
        }
        for (double coefficient : constraint.coefficients) {
            if (!std::isfinite(coefficient)) {
                error = "Non-finite constraint coefficient.";
                return false;
            }
        }
    }
    return true;
}

bool isTerminalEvent(const std::string& event) {
    return event == "optimal" || event == "infeasible" ||
           event == "unbounded" || event == "iteration_limit" ||
           event == "invalid_model";
}

void appendTrace(
    SimplexResult& result,
    TableauState& state,
    const std::string& phase,
    const std::string& event,
    int iteration,
    const std::string& explanation,
    int enteringColumn = -1,
    int leavingRow = -1,
    double pivotValue = 0.0,
    const std::vector<RatioTestEntry>& ratioTests = {}
) {
    SolverTraceStep step;
    step.phase = phase;
    step.event = event;
    step.iteration = iteration;
    step.explanation = explanation;
    step.columnNames = state.columnNames;
    step.pivotValue = pivotValue;
    step.ratioTests = ratioTests;

    // Preserve the exact row operations that the pivot() routine will apply.
    // The pivot event captures the tableau *before* the pivot is applied.
    // First normalize the leaving row, then eliminate the entering column
    // from every other constraint row and the objective row.
    if (event == "pivot" && enteringColumn >= 0 &&
        enteringColumn < state.totalVariables && leavingRow >= 0 &&
        leavingRow < static_cast<int>(state.basis.size()) &&
        std::isfinite(pivotValue) && std::abs(pivotValue) > EPS) {
        RowOperation normalize;
        normalize.targetRow = leavingRow + 1;
        normalize.sourceRow = leavingRow + 1;
        normalize.operation = "divide";
        normalize.factor = pivotValue;
        step.rowOperations.push_back(normalize);

        const int objectiveRow = static_cast<int>(state.basis.size());
        for (int i = 0; i <= objectiveRow; ++i) {
            if (i == leavingRow) continue;
            const double factor = state.tableau[i][enteringColumn];
            if (std::abs(factor) <= EPS) continue;

            RowOperation eliminate;
            eliminate.targetRow = i + 1;
            eliminate.sourceRow = leavingRow + 1;
            eliminate.operation = "subtract_multiple";
            eliminate.factor = factor;
            step.rowOperations.push_back(eliminate);
        }
    }

    // Record the objective-row coefficient for every column at the exact
    // decision state. Under this tableau convention, negative coefficients
    // are candidates to enter; Bland's rule selects the first eligible
    // non-artificial column, not necessarily the most negative one.
    if (state.tableau.size() == state.basis.size() + 1 &&
        !state.tableau.empty()) {
        const std::size_t objectiveRow = state.basis.size();
        step.reducedCosts.reserve(state.columnNames.size());
        for (std::size_t j = 0; j < state.columnNames.size(); ++j) {
            ReducedCostEntry candidate;
            candidate.variable = state.columnNames[j];
            candidate.tableauCoefficient = state.tableau[objectiveRow][j];
            candidate.artificial = j < state.artificial.size() && state.artificial[j];
            candidate.eligible = !candidate.artificial &&
                                 candidate.tableauCoefficient < -EPS;
            candidate.selected = static_cast<int>(j) == enteringColumn;
            step.reducedCosts.push_back(std::move(candidate));
        }
    }

    if (enteringColumn >= 0 && enteringColumn < static_cast<int>(state.columnNames.size())) {
        step.enteringVariable = state.columnNames[enteringColumn];
        step.pivotColumn = enteringColumn + 1;
    }
    if (leavingRow >= 0 && leavingRow < static_cast<int>(state.basis.size())) {
        const int oldBasic = state.basis[leavingRow];
        if (oldBasic >= 0 && oldBasic < static_cast<int>(state.columnNames.size())) {
            step.leavingVariable = state.columnNames[oldBasic];
        }
        step.pivotRow = leavingRow + 1;
    }

    step.basis.reserve(state.basis.size());
    for (int basic : state.basis) {
        if (basic >= 0 && basic < static_cast<int>(state.columnNames.size())) {
            step.basis.push_back(state.columnNames[basic]);
        } else {
            step.basis.push_back("?");
        }
    }

    const bool hasRoomForStep = result.trace.size() < MAX_TRACE_EVENTS;
    if (!hasRoomForStep) {
        result.traceTruncated = true;
        // Preserve the final status event even if the event cap was reached.
        if (isTerminalEvent(event) && !result.trace.empty()) {
            result.trace.back() = std::move(step);
            result.trace.back().tableauRecorded = false;
        }
        return;
    }

    std::size_t cellCount = 0;
    for (const auto& row : state.tableau) {
        cellCount += row.size();
    }

    if (state.traceTableauCells + cellCount <= MAX_TRACE_TABLEAU_CELLS) {
        step.tableau = state.tableau;
        step.tableauRecorded = true;
        state.traceTableauCells += cellCount;
    } else {
        step.tableauRecorded = false;
        result.traceTruncated = true;
    }
    result.trace.push_back(std::move(step));
}

std::vector<NormalizedConstraint> normalizeConstraints(const LPP& model) {
    std::vector<NormalizedConstraint> normalized;
    normalized.reserve(model.constraints.size());

    for (const auto& source : model.constraints) {
        NormalizedConstraint row{source.coefficients, source.relation, source.rhs};
        if (row.rhs < -EPS) {
            for (double& value : row.coefficients) {
                value = -value;
            }
            row.rhs = -row.rhs;
            if (row.relation == "<=") {
                row.relation = ">=";
            } else if (row.relation == ">=") {
                row.relation = "<=";
            }
        } else if (std::abs(row.rhs) <= EPS) {
            row.rhs = 0.0;
        }
        normalized.push_back(std::move(row));
    }
    return normalized;
}

bool prepareTableau(
    const LPP& model,
    const std::vector<NormalizedConstraint>& constraints,
    TableauState& state
) {
    state.originalVariables = static_cast<int>(model.objective.size());
    const int m = static_cast<int>(constraints.size());

    int total = state.originalVariables;
    for (const auto& constraint : constraints) {
        if (constraint.relation == "<=") {
            total += 1; // slack
        } else if (constraint.relation == ">=") {
            total += 2; // surplus and artificial
        } else {
            total += 1; // artificial for equality
        }
    }

    state.totalVariables = total;
    state.rhsColumn = total;
    state.tableau.assign(m + 1, std::vector<double>(total + 1, 0.0));
    state.basis.assign(m, -1);
    state.artificial.assign(total, false);
    state.columnNames.assign(total, "");
    for (int j = 0; j < state.originalVariables; ++j) {
        state.columnNames[j] = "x" + std::to_string(j + 1);
    }

    int nextColumn = state.originalVariables;
    for (int i = 0; i < m; ++i) {
        const auto& constraint = constraints[i];
        for (int j = 0; j < state.originalVariables; ++j) {
            state.tableau[i][j] = constraint.coefficients[j];
        }
        state.tableau[i][state.rhsColumn] = std::max(0.0, constraint.rhs);

        const std::string rowNumber = std::to_string(i + 1);
        if (constraint.relation == "<=") {
            state.tableau[i][nextColumn] = 1.0;
            state.columnNames[nextColumn] = "s" + rowNumber;
            state.basis[i] = nextColumn;
            ++nextColumn;
        } else if (constraint.relation == ">=") {
            state.tableau[i][nextColumn] = -1.0; // surplus
            state.columnNames[nextColumn] = "e" + rowNumber;
            ++nextColumn;
            state.tableau[i][nextColumn] = 1.0;  // artificial
            state.columnNames[nextColumn] = "a" + rowNumber;
            state.artificial[nextColumn] = true;
            state.basis[i] = nextColumn;
            ++nextColumn;
        } else {
            state.tableau[i][nextColumn] = 1.0;
            state.columnNames[nextColumn] = "a" + rowNumber;
            state.artificial[nextColumn] = true;
            state.basis[i] = nextColumn;
            ++nextColumn;
        }
    }
    return nextColumn == total;
}

void setCanonicalObjective(
    TableauState& state,
    const std::vector<double>& costs
) {
    const int m = static_cast<int>(state.basis.size());
    auto& objectiveRow = state.tableau[m];
    std::fill(objectiveRow.begin(), objectiveRow.end(), 0.0);

    for (int j = 0; j < state.totalVariables; ++j) {
        objectiveRow[j] = -costs[j];
    }

    // Eliminate all current basic columns from the objective row.
    for (int i = 0; i < m; ++i) {
        const int basicColumn = state.basis[i];
        const double factor = objectiveRow[basicColumn];
        if (std::abs(factor) <= EPS) {
            objectiveRow[basicColumn] = 0.0;
            continue;
        }
        for (int j = 0; j <= state.rhsColumn; ++j) {
            objectiveRow[j] -= factor * state.tableau[i][j];
        }
        objectiveRow[basicColumn] = 0.0;
    }
}

void pivot(TableauState& state, int leavingRow, int enteringColumn) {
    const int m = static_cast<int>(state.basis.size());
    const double pivotValue = state.tableau[leavingRow][enteringColumn];

    for (int j = 0; j <= state.rhsColumn; ++j) {
        state.tableau[leavingRow][j] /= pivotValue;
    }
    state.tableau[leavingRow][enteringColumn] = 1.0;

    for (int i = 0; i <= m; ++i) {
        if (i == leavingRow) {
            continue;
        }
        const double factor = state.tableau[i][enteringColumn];
        if (std::abs(factor) <= EPS) {
            state.tableau[i][enteringColumn] = 0.0;
            continue;
        }
        for (int j = 0; j <= state.rhsColumn; ++j) {
            state.tableau[i][j] -= factor * state.tableau[leavingRow][j];
        }
        state.tableau[i][enteringColumn] = 0.0;
    }

    state.basis[leavingRow] = enteringColumn;
}

enum class IterationStatus { Optimal, Unbounded, IterationLimit };

IterationStatus optimize(
    TableauState& state,
    int maxIterations,
    int& iterations,
    SimplexResult& result,
    const std::string& phase,
    const std::string& startExplanation
) {
    const int m = static_cast<int>(state.basis.size());
    const int objectiveRow = m;

    appendTrace(result, state, phase, "phase_start", iterations, startExplanation);

    while (true) {
        // Bland's rule: first eligible non-artificial variable.
        int entering = -1;
        for (int j = 0; j < state.totalVariables; ++j) {
            if (!state.artificial[j] && state.tableau[objectiveRow][j] < -EPS) {
                entering = j;
                break;
            }
        }

        if (entering == -1) {
            appendTrace(
                result, state, phase, "optimal", iterations,
                "No eligible negative reduced-cost coefficient remains. This phase's objective is optimal."
            );
            return IterationStatus::Optimal;
        }
        if (iterations >= maxIterations) {
            appendTrace(
                result, state, phase, "iteration_limit", iterations,
                "The configured pivot-iteration limit was reached before optimality was established."
            );
            return IterationStatus::IterationLimit;
        }

        int leaving = -1;
        double bestRatio = std::numeric_limits<double>::infinity();
        std::vector<RatioTestEntry> ratioTests;
        ratioTests.reserve(m);

        for (int i = 0; i < m; ++i) {
            const double pivotCandidate = state.tableau[i][entering];
            double rhs = state.tableau[i][state.rhsColumn];
            if (rhs < 0.0 && rhs > -FEASIBILITY_EPS) {
                rhs = 0.0;
            }

            RatioTestEntry candidate;
            const int basicColumn = state.basis[i];
            if (basicColumn >= 0 && basicColumn < static_cast<int>(state.columnNames.size())) {
                candidate.basicVariable = state.columnNames[basicColumn];
            } else {
                candidate.basicVariable = "?";
            }
            candidate.rhs = rhs;
            candidate.enteringCoefficient = pivotCandidate;
            candidate.eligible = pivotCandidate > EPS;

            if (candidate.eligible) {
                candidate.ratio = rhs / pivotCandidate;
                if (candidate.ratio < bestRatio - EPS ||
                    (std::abs(candidate.ratio - bestRatio) <= EPS &&
                     (leaving == -1 || state.basis[i] < state.basis[leaving]))) {
                    bestRatio = candidate.ratio;
                    leaving = i;
                }
            }
            ratioTests.push_back(std::move(candidate));
        }

        if (leaving == -1) {
            appendTrace(
                result, state, phase, "unbounded", iterations,
                "The entering column has no positive pivot candidate, so the objective can improve without a finite leaving variable.",
                entering, -1, 0.0, ratioTests
            );
            return IterationStatus::Unbounded;
        }

        const double pivotValue = state.tableau[leaving][entering];
        appendTrace(
            result, state, phase, "pivot", iterations + 1,
            "Apply the minimum-ratio test. Pivot on the intersection of the entering column and leaving row, then eliminate the entering variable from the other rows.",
            entering, leaving, pivotValue, ratioTests
        );

        pivot(state, leaving, entering);
        ++iterations;
    }
}

std::vector<double> normalizedObjective(const LPP& model, int totalVariables) {
    std::vector<double> costs(totalVariables, 0.0);
    const double sign = model.maximize ? 1.0 : -1.0;
    for (std::size_t j = 0; j < model.objective.size(); ++j) {
        costs[j] = sign * model.objective[j];
    }
    return costs;
}

SimplexResult extractResult(
    const LPP& model,
    const TableauState& state,
    int iterations,
    SolveMethod method,
    const SimplexResult& traceSource
) {
    SimplexResult result;
    result.status = SolveStatus::Optimal;
    result.iterations = iterations;
    result.method = solveMethodName(method);
    result.trace = traceSource.trace;
    result.traceTruncated = traceSource.traceTruncated;
    result.variableValues.assign(state.originalVariables, 0.0);

    for (std::size_t i = 0; i < state.basis.size(); ++i) {
        const int basicColumn = state.basis[i];
        if (basicColumn >= 0 && basicColumn < state.originalVariables) {
            double value = state.tableau[i][state.rhsColumn];
            if (std::abs(value) < FEASIBILITY_EPS) {
                value = 0.0;
            }
            if (value < 0.0 && value > -FEASIBILITY_EPS) {
                value = 0.0;
            }
            result.variableValues[basicColumn] = value;
        }
    }

    result.objectiveValue = 0.0;
    for (std::size_t i = 0; i < model.objective.size(); ++i) {
        result.objectiveValue += model.objective[i] * result.variableValues[i];
    }
    if (std::abs(result.objectiveValue) < FEASIBILITY_EPS) {
        result.objectiveValue = 0.0;
    }

    result.message = "Optimal solution found using ";
    result.message += solveMethodName(method);
    result.message += ".";
    return result;
}

SimplexResult runSimplexFamily(
    const LPP& model,
    SolveMethod method,
    int maxIterations
) {
    SimplexResult result;
    result.status = SolveStatus::InvalidModel;
    result.method = solveMethodName(method);

    std::string validationError;
    if (!validateModel(model, maxIterations, validationError)) {
        result.message = validationError;
        return result;
    }

    if (method == SolveMethod::Simplex) {
        for (const auto& constraint : model.constraints) {
            if (constraint.relation != "<=") {
                result.status = SolveStatus::Unsupported;
                result.message = "Standard Simplex currently requires <= constraints; use Two-Phase or Big-M for >= and = constraints.";
                return result;
            }
            if (constraint.rhs < -EPS) {
                result.status = SolveStatus::Unsupported;
                result.message = "Standard Simplex requires nonnegative RHS values; use Two-Phase or Big-M for negative RHS values.";
                return result;
            }
        }
    }

    const bool needsNormalization = method != SolveMethod::Simplex;
    std::vector<NormalizedConstraint> constraints;
    if (needsNormalization) {
        constraints = normalizeConstraints(model);
    } else {
        constraints.reserve(model.constraints.size());
        for (const auto& source : model.constraints) {
            NormalizedConstraint row{source.coefficients, source.relation, source.rhs};
            if (std::abs(row.rhs) <= EPS) row.rhs = 0.0;
            constraints.push_back(std::move(row));
        }
    }

    TableauState state;
    if (!prepareTableau(model, constraints, state)) {
        result.message = "Could not construct the simplex tableau.";
        return result;
    }

    int iterations = 0;

    if (method == SolveMethod::Simplex) {
        auto costs = normalizedObjective(model, state.totalVariables);
        setCanonicalObjective(state, costs);
        const auto status = optimize(
            state, maxIterations, iterations, result, "simplex",
            "Initial canonical tableau for the selected Standard Simplex objective."
        );
        if (status == IterationStatus::Unbounded) {
            result.status = SolveStatus::Unbounded;
            result.message = "The objective is unbounded in the selected direction.";
            result.iterations = iterations;
            return result;
        }
        if (status == IterationStatus::IterationLimit) {
            result.status = SolveStatus::IterationLimit;
            result.message = "Maximum iteration count reached.";
            result.iterations = iterations;
            return result;
        }
        return extractResult(model, state, iterations, method, result);
    }

    if (method == SolveMethod::TwoPhase) {
        // Phase I maximizes -sum(artificial variables).
        std::vector<double> phaseOneCosts(state.totalVariables, 0.0);
        for (int j = 0; j < state.totalVariables; ++j) {
            if (state.artificial[j]) phaseOneCosts[j] = -1.0;
        }
        setCanonicalObjective(state, phaseOneCosts);

        const auto phaseOneStatus = optimize(
            state, maxIterations, iterations, result, "phase_i",
            "Phase I maximizes the negative sum of artificial variables to find a feasible basis."
        );
        if (phaseOneStatus == IterationStatus::Unbounded) {
            result.status = SolveStatus::InvalidModel;
            result.message = "Phase I unexpectedly became unbounded; numerical failure suspected.";
            result.iterations = iterations;
            appendTrace(result, state, "phase_i", "invalid_model", iterations, result.message);
            return result;
        }
        if (phaseOneStatus == IterationStatus::IterationLimit) {
            result.status = SolveStatus::IterationLimit;
            result.message = "Maximum iteration count reached during Phase I.";
            result.iterations = iterations;
            return result;
        }

        if (state.tableau[state.basis.size()][state.rhsColumn] < -FEASIBILITY_EPS) {
            result.status = SolveStatus::Infeasible;
            result.message = "The constraints are infeasible (Phase I could not drive artificial variables to zero).";
            result.iterations = iterations;
            appendTrace(result, state, "phase_i", "infeasible", iterations, result.message);
            return result;
        }

        // Phase I can finish with artificial variables still basic at value
        // zero, especially when the constraints are redundant or degenerate.
        // They must be pivoted out (or their redundant row removed) before
        // Phase II. Merely banning artificial columns from entering is not
        // sufficient: a Phase II pivot elsewhere can make a basic artificial
        // variable positive and produce a solution that violates the model.
        std::size_t cleanupRow = 0;
        while (cleanupRow < state.basis.size()) {
            const int basicColumn = state.basis[cleanupRow];
            if (basicColumn < 0 || basicColumn >= state.totalVariables) {
                result.status = SolveStatus::InvalidModel;
                result.message = "Invalid basis encountered during Phase I cleanup.";
                result.iterations = iterations;
                appendTrace(result, state, "phase_i", "invalid_model", iterations, result.message);
                return result;
            }
            if (!state.artificial[basicColumn]) {
                ++cleanupRow;
                continue;
            }

            double& rhs = state.tableau[cleanupRow][state.rhsColumn];
            if (std::abs(rhs) <= FEASIBILITY_EPS) {
                rhs = 0.0;
            } else {
                result.status = SolveStatus::Infeasible;
                result.message = "An artificial variable remained positive after Phase I; the model is infeasible or numerically unstable.";
                result.iterations = iterations;
                appendTrace(result, state, "phase_i", "infeasible", iterations, result.message);
                return result;
            }

            int enteringCleanup = -1;
            for (int j = 0; j < state.totalVariables; ++j) {
                if (state.artificial[j]) continue;
                if (std::find(state.basis.begin(), state.basis.end(), j) != state.basis.end()) continue;
                if (std::abs(state.tableau[cleanupRow][j]) > EPS) {
                    enteringCleanup = j;
                    break;
                }
            }

            if (enteringCleanup >= 0) {
                const double pivotValue = state.tableau[cleanupRow][enteringCleanup];
                appendTrace(
                    result, state, "phase_i", "pivot", iterations,
                    "Phase I cleanup: pivot a zero-valued artificial basic variable out before Phase II.",
                    enteringCleanup, static_cast<int>(cleanupRow), pivotValue
                );
                pivot(state, static_cast<int>(cleanupRow), enteringCleanup);
                ++cleanupRow;
            } else {
                // No original/slack/surplus column can replace this zero-valued
                // artificial basic variable, so this constraint row is redundant.
                appendTrace(
                    result, state, "phase_i", "redundant_row_removed", iterations,
                    "Phase I cleanup: this zero-valued artificial row has no non-artificial pivot candidate and is redundant."
                );
                state.tableau.erase(state.tableau.begin() + static_cast<std::ptrdiff_t>(cleanupRow));
                state.basis.erase(state.basis.begin() + static_cast<std::ptrdiff_t>(cleanupRow));
            }
        }

        appendTrace(
            result, state, "phase_i", "phase_transition", iterations,
            "Phase I found a feasible basis and removed all artificial basic variables. The solver now replaces the auxiliary objective with the original objective for Phase II."
        );

        // Phase II optimizes the true objective. Artificial columns remain in
        // the tableau, but are nonbasic and never allowed to enter the basis.
        auto phaseTwoCosts = normalizedObjective(model, state.totalVariables);
        for (int j = 0; j < state.totalVariables; ++j) {
            if (state.artificial[j]) phaseTwoCosts[j] = 0.0;
        }
        setCanonicalObjective(state, phaseTwoCosts);

        const auto phaseTwoStatus = optimize(
            state, maxIterations, iterations, result, "phase_ii",
            "Phase II uses the original objective with the feasible Phase I basis. Artificial columns cannot enter the basis."
        );
        if (phaseTwoStatus == IterationStatus::Unbounded) {
            result.status = SolveStatus::Unbounded;
            result.message = "The objective is unbounded in the selected direction.";
            result.iterations = iterations;
            return result;
        }
        if (phaseTwoStatus == IterationStatus::IterationLimit) {
            result.status = SolveStatus::IterationLimit;
            result.message = "Maximum iteration count reached during Phase II.";
            result.iterations = iterations;
            return result;
        }

        return extractResult(model, state, iterations, method, result);
    }

    // Big-M: penalize artificial variables in the normalized maximization
    // objective. A finite M is practical but may be numerically delicate.
    double scale = 1.0;
    for (double value : model.objective) scale = std::max(scale, std::abs(value));
    for (const auto& constraint : constraints) {
        scale = std::max(scale, std::abs(constraint.rhs));
        for (double value : constraint.coefficients) {
            scale = std::max(scale, std::abs(value));
        }
    }
    const double bigM = std::min(1e12, 1e6 * scale);

    auto costs = normalizedObjective(model, state.totalVariables);
    for (int j = 0; j < state.totalVariables; ++j) {
        if (state.artificial[j]) costs[j] = -bigM;
    }
    setCanonicalObjective(state, costs);

    const auto status = optimize(
        state, maxIterations, iterations, result, "big_m",
        "Initial Big-M tableau. Artificial variables carry a large penalty in the normalized objective."
    );
    if (status == IterationStatus::Unbounded) {
        result.status = SolveStatus::Unbounded;
        result.message = "The objective is unbounded in the selected direction.";
        result.iterations = iterations;
        return result;
    }
    if (status == IterationStatus::IterationLimit) {
        result.status = SolveStatus::IterationLimit;
        result.message = "Maximum iteration count reached.";
        result.iterations = iterations;
        return result;
    }

    double artificialSum = 0.0;
    for (std::size_t i = 0; i < state.basis.size(); ++i) {
        if (state.artificial[state.basis[i]]) {
            artificialSum += std::max(0.0, state.tableau[i][state.rhsColumn]);
        }
    }
    if (artificialSum > FEASIBILITY_EPS) {
        result.status = SolveStatus::Infeasible;
        result.message = "The constraints appear infeasible under the Big-M penalty; verify numerical scaling or use Two-Phase.";
        result.iterations = iterations;
        appendTrace(result, state, "big_m", "infeasible", iterations, result.message);
        return result;
    }

    return extractResult(model, state, iterations, method, result);
}
} // namespace

const char* solveMethodName(SolveMethod method) {
    switch (method) {
        case SolveMethod::Simplex: return "simplex";
        case SolveMethod::TwoPhase: return "two_phase";
        case SolveMethod::BigM: return "big_m";
    }
    return "simplex";
}

SimplexResult solveLPP(const LPP& model, SolveMethod method, int maxIterations) {
    return runSimplexFamily(model, method, maxIterations);
}

SimplexResult solveSimplex(const LPP& model, int maxIterations) {
    return solveLPP(model, SolveMethod::Simplex, maxIterations);
}

SimplexResult solveTwoPhase(const LPP& model, int maxIterations) {
    return solveLPP(model, SolveMethod::TwoPhase, maxIterations);
}

SimplexResult solveBigM(const LPP& model, int maxIterations) {
    return solveLPP(model, SolveMethod::BigM, maxIterations);
}
