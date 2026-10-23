#include "../solver/lpp.h"
#include "../solver/simplex.h"

#include <cmath>
#include <iostream>
#include <string>
#include <vector>

using namespace std;

int passed = 0;
int failed = 0;

bool near(double a, double b, double tolerance = 1e-6) {
    return std::abs(a - b) <= tolerance;
}

void check(bool condition, const string& name) {
    if (condition) {
        cout << "[PASS] " << name << '\n';
        ++passed;
    } else {
        cout << "[FAIL] " << name << '\n';
        ++failed;
    }
}

bool hasSolution(const SimplexResult& result, double z, double x, double y) {
    return result.status == SolveStatus::Optimal &&
           near(result.objectiveValue, z) &&
           result.variableValues.size() == 2 &&
           near(result.variableValues[0], x) &&
           near(result.variableValues[1], y);
}

LPP classicMax() {
    LPP model;
    model.maximize = true;
    model.objective = {3, 5};
    model.constraints = {
        {{1, 0}, "<=", 4},
        {{0, 2}, "<=", 12},
        {{3, 2}, "<=", 18}
    };
    return model;
}

LPP mixedConstraintMax() {
    LPP model;
    model.maximize = true;
    model.objective = {3, 2};
    model.constraints = {
        {{1, 1}, "<=", 4},
        {{1, 0}, ">=", 1},
        {{0, 1}, ">=", 1}
    };
    return model;
}

void testClassicSimplex() {
    const auto result = solveSimplex(classicMax());
    check(hasSolution(result, 36, 2, 6), "Simplex: solve known maximization problem");
}

void testSimplexSupportsMinimizationForStandardForm() {
    LPP model;
    model.maximize = false;
    model.objective = {-1};
    model.constraints = {{{1}, "<=", 5}};
    const auto result = solveSimplex(model);
    check(result.status == SolveStatus::Optimal && near(result.objectiveValue, -5) &&
          result.variableValues.size() == 1 && near(result.variableValues[0], 5),
          "Simplex: minimize with a feasible slack basis");
}

void testSimplexRejectsMixedConstraints() {
    const auto result = solveSimplex(mixedConstraintMax());
    check(result.status == SolveStatus::Unsupported,
          "Simplex: clearly reject mixed constraints that require Phase I");
}

void testTwoPhaseMixedConstraints() {
    const auto result = solveTwoPhase(mixedConstraintMax());
    check(hasSolution(result, 11, 3, 1), "Two-Phase: solve mixed <= and >= constraints");
}

void testBigMMixedConstraints() {
    const auto result = solveBigM(mixedConstraintMax());
    check(hasSolution(result, 11, 3, 1), "Big-M: solve mixed <= and >= constraints");
}

void testEqualityConstraint() {
    LPP model;
    model.maximize = true;
    model.objective = {3, 2};
    model.constraints = {
        {{1, 1}, "=", 4},
        {{1, 0}, "<=", 3},
        {{0, 1}, "<=", 3}
    };
    const auto phase = solveTwoPhase(model);
    const auto bigM = solveBigM(model);
    check(hasSolution(phase, 11, 3, 1), "Two-Phase: handle equality constraint");
    check(hasSolution(bigM, 11, 3, 1), "Big-M: handle equality constraint");
}

void testNegativeRhsNormalization() {
    LPP model;
    model.maximize = true;
    model.objective = {3, 2};
    model.constraints = {
        {{-1, 0}, "<=", -1},  // x >= 1 after normalization
        {{1, 1}, "<=", 4},
        {{1, 0}, "<=", 3}
    };
    const auto phase = solveTwoPhase(model);
    const auto bigM = solveBigM(model);
    check(hasSolution(phase, 11, 3, 1), "Two-Phase: normalize negative RHS");
    check(hasSolution(bigM, 11, 3, 1), "Big-M: normalize negative RHS");
}

void testMinimizationWithMixedConstraints() {
    LPP model;
    model.maximize = false;
    model.objective = {1, 2};
    model.constraints = {
        {{1, 1}, ">=", 4},
        {{1, 0}, "<=", 3},
        {{0, 1}, "<=", 3}
    };
    const auto phase = solveTwoPhase(model);
    const auto bigM = solveBigM(model);
    check(hasSolution(phase, 5, 3, 1), "Two-Phase: solve minimization with mixed constraints");
    check(hasSolution(bigM, 5, 3, 1), "Big-M: solve minimization with mixed constraints");
}

void testInfeasibleProblem() {
    LPP model;
    model.maximize = true;
    model.objective = {1};
    model.constraints = {
        {{1}, "<=", 1},
        {{1}, ">=", 2}
    };
    const auto phase = solveTwoPhase(model);
    const auto bigM = solveBigM(model);
    check(phase.status == SolveStatus::Infeasible,
          "Two-Phase: identify infeasible constraints");
    check(bigM.status == SolveStatus::Infeasible,
          "Big-M: identify infeasible constraints");
}

void testUnboundedProblem() {
    LPP model;
    model.maximize = true;
    model.objective = {1};
    model.constraints = {{{1}, ">=", 1}};
    check(solveTwoPhase(model).status == SolveStatus::Unbounded,
          "Two-Phase: detect unbounded objective");
    check(solveBigM(model).status == SolveStatus::Unbounded,
          "Big-M: detect unbounded objective");
}

void testZeroOptimalSolution() {
    LPP model;
    model.maximize = true;
    model.objective = {-1};
    model.constraints = {{{1}, "<=", 10}};
    const auto result = solveSimplex(model);
    check(result.status == SolveStatus::Optimal && near(result.objectiveValue, 0) &&
          result.variableValues.size() == 1 && near(result.variableValues[0], 0),
          "Simplex: handle optimum at the origin");
}

void testInvalidDimensions() {
    LPP model;
    model.maximize = true;
    model.objective = {1, 2};
    model.constraints = {{{1}, "<=", 5}};
    check(solveTwoPhase(model).status == SolveStatus::InvalidModel,
          "Reject mismatched model dimensions");
}

void testSimplexRejectsNegativeRhs() {
    LPP model;
    model.maximize = true;
    model.objective = {1};
    model.constraints = {{{-1}, "<=", -1}};
    check(solveSimplex(model).status == SolveStatus::Unsupported,
          "Standard Simplex: direct user to Phase I for negative RHS");
}

void testDuplicateEqualities() {
    LPP model;
    model.maximize = true;
    model.objective = {3, 2};
    model.constraints = {
        {{1, 1}, "=", 4},
        {{2, 2}, "=", 8}
    };
    const auto result = solveTwoPhase(model);
    check(result.status == SolveStatus::Optimal && near(result.objectiveValue, 12) &&
          result.variableValues.size() == 2 && near(result.variableValues[0], 4) &&
          near(result.variableValues[1], 0),
          "Two-Phase: handle redundant equality/artificial basis");
}

void testThreeVariableModels() {
    LPP model;
    model.maximize = true;
    model.objective = {1, 1, 1};
    model.constraints = {
        {{1, 0, 0}, "<=", 2},
        {{0, 1, 0}, "<=", 3},
        {{0, 0, 1}, "<=", 4},
        {{1, 1, 1}, "<=", 9}
    };

    const auto phase = solveTwoPhase(model);
    const auto bigM = solveBigM(model);
    const auto matchesKnownOptimum = [](const SimplexResult& result) {
        return result.status == SolveStatus::Optimal &&
               near(result.objectiveValue, 9) &&
               result.variableValues.size() == 3 &&
               near(result.variableValues[0], 2) &&
               near(result.variableValues[1], 3) &&
               near(result.variableValues[2], 4);
    };

    check(matchesKnownOptimum(phase),
          "Two-Phase: solve a three-variable model");
    check(matchesKnownOptimum(bigM),
          "Big-M: solve a three-variable model");
}


void testSimplexTraceContainsPivotTableaux() {
    const auto result = solveSimplex(classicMax());
    bool hasPivot = false;
    bool hasTerminalOptimal = false;
    bool validPivotSnapshot = false;

    for (const auto& step : result.trace) {
        if (step.event == "pivot") {
            hasPivot = true;
            validPivotSnapshot = validPivotSnapshot ||
                (step.tableauRecorded && !step.tableau.empty() &&
                 !step.enteringVariable.empty() && !step.leavingVariable.empty() &&
                 step.pivotValue > 0.0 && step.pivotRow > 0 && step.pivotColumn > 0);
        }
        if (step.event == "optimal" && step.phase == "simplex") {
            hasTerminalOptimal = true;
        }
    }

    check(!result.trace.empty() && result.trace.front().event == "phase_start",
          "Trace: record the initial Standard Simplex tableau");
    check(hasPivot && validPivotSnapshot,
          "Trace: record actual entering/leaving variables and pivot tableau");
    check(hasTerminalOptimal,
          "Trace: record Standard Simplex termination");
}

void testTwoPhaseTraceIncludesPhaseTransition() {
    const auto result = solveTwoPhase(mixedConstraintMax());
    bool phaseOne = false;
    bool transition = false;
    bool phaseTwo = false;

    for (const auto& step : result.trace) {
        phaseOne = phaseOne || step.phase == "phase_i";
        transition = transition || step.event == "phase_transition";
        phaseTwo = phaseTwo || step.phase == "phase_ii";
    }

    check(phaseOne && transition && phaseTwo,
          "Trace: show Phase I, transition, and Phase II");
    check(result.status == SolveStatus::Optimal && !result.traceTruncated,
          "Trace: retain complete trace for a small Two-Phase model");
}

void testBigMTraceNamesArtificialVariables() {
    const auto result = solveBigM(mixedConstraintMax());
    bool bigMStart = false;
    bool artificialColumn = false;

    for (const auto& step : result.trace) {
        if (step.phase == "big_m" && step.event == "phase_start") {
            bigMStart = true;
            for (const auto& name : step.columnNames) {
                if (!name.empty() && name[0] == 'a') artificialColumn = true;
            }
        }
    }

    check(bigMStart && artificialColumn,
          "Trace: show Big-M initial tableau and artificial-variable columns");
}

void testMinimumRatioTestIsRecorded() {
    LPP model;
    model.maximize = true;
    model.objective = {4, 3};
    model.constraints = {
        {{1, 1}, "<=", 4},
        {{1, 0}, "<=", 2},
        {{0, 1}, "<=", 3}
    };

    const auto result = solveSimplex(model);
    const SolverTraceStep* firstPivot = nullptr;
    for (const auto& step : result.trace) {
        if (step.event == "pivot") {
            firstPivot = &step;
            break;
        }
    }

    check(firstPivot != nullptr, "Ratio trace: record a first pivot step");
    if (!firstPivot) return;

    check(firstPivot->ratioTests.size() == 3,
          "Ratio trace: record one candidate per constraint row");
    if (firstPivot->ratioTests.size() != 3) return;

    check(firstPivot->ratioTests[0].eligible &&
          near(firstPivot->ratioTests[0].ratio, 4.0),
          "Ratio trace: compute first candidate ratio 4/1 = 4");
    check(firstPivot->ratioTests[1].eligible &&
          near(firstPivot->ratioTests[1].ratio, 2.0) &&
          firstPivot->leavingVariable == "s2",
          "Ratio trace: select the minimum ratio 2 and leave s2");
    check(!firstPivot->ratioTests[2].eligible,
          "Ratio trace: mark nonpositive pivot coefficients ineligible");
}

void testReducedCostTraceExplainsBlandsRule() {
    // x2 has the more-negative coefficient (-5), but Bland's rule chooses x1
    // because x1 is the first eligible non-artificial column in column order.
    const auto result = solveSimplex(classicMax());
    const SolverTraceStep* firstPivot = nullptr;
    for (const auto& step : result.trace) {
        if (step.event == "pivot") {
            firstPivot = &step;
            break;
        }
    }

    check(firstPivot != nullptr,
          "Reduced-cost trace: record the first entering-variable decision");
    if (!firstPivot) return;

    const auto findCost = [&](const std::string& variable) -> const ReducedCostEntry* {
        for (const auto& item : firstPivot->reducedCosts) {
            if (item.variable == variable) return &item;
        }
        return nullptr;
    };
    const auto* x1 = findCost("x1");
    const auto* x2 = findCost("x2");

    check(x1 && near(x1->tableauCoefficient, -3.0) && x1->eligible && x1->selected,
          "Reduced-cost trace: select x1 from its recorded -3 objective-row coefficient");
    check(x2 && near(x2->tableauCoefficient, -5.0) && x2->eligible && !x2->selected,
          "Reduced-cost trace: show x2 is eligible but later in Bland's order");
    check(firstPivot->enteringVariable == "x1",
          "Reduced-cost trace: explain Bland's rule rather than selecting the most negative");
}

void testPivotRowOperationsReconstructNextTableau() {
    const auto result = solveSimplex(classicMax());
    std::size_t pivotIndex = result.trace.size();
    for (std::size_t i = 0; i < result.trace.size(); ++i) {
        if (result.trace[i].event == "pivot") {
            pivotIndex = i;
            break;
        }
    }

    check(pivotIndex < result.trace.size(),
          "Row-operation trace: record a pivot event");
    if (pivotIndex >= result.trace.size()) return;

    const auto& pivotStep = result.trace[pivotIndex];
    check(pivotStep.rowOperations.size() >= 2 &&
          pivotStep.rowOperations.front().operation == "divide" &&
          pivotStep.rowOperations.front().targetRow == pivotStep.pivotRow,
          "Row-operation trace: normalize the selected pivot row first");
    if (pivotStep.rowOperations.empty()) return;

    bool hasElimination = false;
    for (const auto& operation : pivotStep.rowOperations) {
        hasElimination = hasElimination || operation.operation == "subtract_multiple";
    }
    check(hasElimination,
          "Row-operation trace: record elimination operations for other rows");

    if (pivotIndex + 1 >= result.trace.size()) {
        check(false, "Row-operation trace: record the tableau after the pivot");
        return;
    }

    const auto& nextStep = result.trace[pivotIndex + 1];
    if (!pivotStep.tableauRecorded || !nextStep.tableauRecorded ||
        pivotStep.phase != nextStep.phase || pivotStep.tableau.empty() ||
        nextStep.tableau.empty()) {
        check(false, "Row-operation trace: retain before/after tableau snapshots");
        return;
    }

    auto reconstructed = pivotStep.tableau;
    for (const auto& operation : pivotStep.rowOperations) {
        const int target = operation.targetRow - 1;
        const int source = operation.sourceRow - 1;
        if (target < 0 || source < 0 ||
            target >= static_cast<int>(reconstructed.size()) ||
            source >= static_cast<int>(reconstructed.size())) {
            check(false, "Row-operation trace: use valid 1-based row indices");
            return;
        }

        if (operation.operation == "divide") {
            for (double& value : reconstructed[target]) {
                value /= operation.factor;
            }
        } else if (operation.operation == "subtract_multiple") {
            for (std::size_t column = 0; column < reconstructed[target].size(); ++column) {
                reconstructed[target][column] -=
                    operation.factor * reconstructed[source][column];
            }
        } else {
            check(false, "Row-operation trace: use a recognized operation");
            return;
        }
    }

    bool matches = reconstructed.size() == nextStep.tableau.size();
    for (std::size_t row = 0; matches && row < reconstructed.size(); ++row) {
        matches = reconstructed[row].size() == nextStep.tableau[row].size();
        for (std::size_t column = 0; matches && column < reconstructed[row].size(); ++column) {
            matches = near(reconstructed[row][column], nextStep.tableau[row][column], 1e-6);
        }
    }
    check(matches,
          "Row-operation trace: applying recorded operations reconstructs the next tableau");
}

void testPhaseOneArtificialCleanupRegression() {
    // Degenerate feasible model that previously exposed a correctness bug:
    // a zero-valued artificial variable stayed basic after Phase I and became
    // positive during a Phase II pivot, allowing an infeasible answer through.
    LPP model;
    model.maximize = true;
    model.objective = {1, -3};
    model.constraints = {
        {{1, 0}, "<=", 5},
        {{0, 1}, "<=", 2},
        {{1, -1}, "<=", 1},
        {{3, 1}, ">=", 2},
        {{1, -4}, "=", -8},
        {{-4, -2}, "=", -4}
    };

    const auto phase = solveTwoPhase(model);
    const auto bigM = solveBigM(model);
    check(hasSolution(phase, -6, 0, 2),
          "Two-Phase: remove zero-valued artificial basics before Phase II");
    check(hasSolution(bigM, -6, 0, 2),
          "Big-M: cross-check degenerate mixed/equality model");

    bool phaseTwoHasNoArtificialBasics = true;
    bool sawPhaseTwo = false;
    for (const auto& step : phase.trace) {
        if (step.phase != "phase_ii") continue;
        sawPhaseTwo = true;
        for (const auto& name : step.basis) {
            if (!name.empty() && name[0] == 'a') {
                phaseTwoHasNoArtificialBasics = false;
            }
        }
    }
    check(sawPhaseTwo && phaseTwoHasNoArtificialBasics,
          "Two-Phase trace: artificial variables are not basic in Phase II");
}

void testInfeasibleTraceRecordsReason() {
    LPP model;
    model.maximize = true;
    model.objective = {1};
    model.constraints = {{{1}, "<=", 1}, {{1}, ">=", 2}};
    const auto result = solveTwoPhase(model);
    bool hasInfeasibleEvent = false;
    for (const auto& step : result.trace) {
        if (step.event == "infeasible") hasInfeasibleEvent = true;
    }
    check(result.status == SolveStatus::Infeasible && hasInfeasibleEvent,
          "Trace: record why Phase I declares an infeasible model");
}

int main() {
    cout << "=== OptiSolve Refactored Solver Tests ===\n\n";
    testClassicSimplex();
    testSimplexSupportsMinimizationForStandardForm();
    testSimplexRejectsMixedConstraints();
    testTwoPhaseMixedConstraints();
    testBigMMixedConstraints();
    testEqualityConstraint();
    testNegativeRhsNormalization();
    testMinimizationWithMixedConstraints();
    testInfeasibleProblem();
    testUnboundedProblem();
    testZeroOptimalSolution();
    testInvalidDimensions();
    testSimplexRejectsNegativeRhs();
    testDuplicateEqualities();
    testThreeVariableModels();
    testSimplexTraceContainsPivotTableaux();
    testTwoPhaseTraceIncludesPhaseTransition();
    testBigMTraceNamesArtificialVariables();
    testMinimumRatioTestIsRecorded();
    testReducedCostTraceExplainsBlandsRule();
    testPivotRowOperationsReconstructNextTableau();
    testPhaseOneArtificialCleanupRegression();
    testInfeasibleTraceRecordsReason();
    cout << "\n===============================\n";
    cout << "Passed: " << passed << '\n';
    cout << "Failed: " << failed << '\n';
    return failed == 0 ? 0 : 1;
}
