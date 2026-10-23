#include "../solver/lpp.h"
#include "../solver/simplex.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {
constexpr double TOL = 1e-7;
int passed = 0;
int failed = 0;

void check(bool condition, const std::string& message) {
    if (condition) {
        std::cout << "[PASS] " << message << '\n';
        ++passed;
    } else {
        std::cout << "[FAIL] " << message << '\n';
        ++failed;
    }
}

bool close(double a, double b, double tolerance = TOL) {
    return std::abs(a - b) <= tolerance;
}

bool reconstructsNextTableau(const SolverTraceStep& before,
                             const SolverTraceStep& after,
                             double& maxDifference) {
    if (!before.tableauRecorded || !after.tableauRecorded ||
        before.tableau.empty() || after.tableau.empty() ||
        before.phase != after.phase) {
        return false;
    }

    auto reconstructed = before.tableau;
    for (const auto& operation : before.rowOperations) {
        const int target = operation.targetRow - 1;
        const int source = operation.sourceRow - 1;
        if (target < 0 || source < 0 ||
            target >= static_cast<int>(reconstructed.size()) ||
            source >= static_cast<int>(reconstructed.size()) ||
            !std::isfinite(operation.factor)) {
            return false;
        }

        if (operation.operation == "divide") {
            if (std::abs(operation.factor) < 1e-12) return false;
            for (double& value : reconstructed[target]) value /= operation.factor;
        } else if (operation.operation == "subtract_multiple") {
            if (reconstructed[target].size() != reconstructed[source].size()) return false;
            for (std::size_t j = 0; j < reconstructed[target].size(); ++j) {
                reconstructed[target][j] -= operation.factor * reconstructed[source][j];
            }
        } else {
            return false;
        }
    }

    if (reconstructed.size() != after.tableau.size()) return false;
    maxDifference = 0.0;
    for (std::size_t i = 0; i < reconstructed.size(); ++i) {
        if (reconstructed[i].size() != after.tableau[i].size()) return false;
        for (std::size_t j = 0; j < reconstructed[i].size(); ++j) {
            maxDifference = std::max(
                maxDifference,
                std::abs(reconstructed[i][j] - after.tableau[i][j])
            );
        }
    }
    return maxDifference <= TOL;
}

bool verifyMethod(const std::string& label, const SimplexResult& result) {
    bool allGood = true;
    int checkedPivots = 0;
    int checkedReducedCosts = 0;
    int checkedRatioTests = 0;

    for (std::size_t i = 0; i < result.trace.size(); ++i) {
        const auto& step = result.trace[i];
        if (step.event != "pivot") continue;
        if (i + 1 >= result.trace.size()) {
            allGood = false;
            continue;
        }
        const auto& next = result.trace[i + 1];
        if (!step.tableauRecorded || !next.tableauRecorded || step.phase != next.phase) {
            allGood = false;
            continue;
        }

        double maxDifference = 0.0;
        if (!reconstructsNextTableau(step, next, maxDifference)) {
            allGood = false;
            continue;
        }
        ++checkedPivots;

        if (next.tableau.empty() || next.reducedCosts.size() != next.columnNames.size() ||
            next.tableau.back().size() < next.reducedCosts.size()) {
            allGood = false;
            continue;
        }
        for (std::size_t j = 0; j < next.reducedCosts.size(); ++j) {
            if (!close(next.reducedCosts[j].tableauCoefficient, next.tableau.back()[j])) {
                allGood = false;
            }
        }
        ++checkedReducedCosts;

        if (next.event == "pivot") {
            bool selectedEnteringMatches = false;
            for (const auto& cost : next.reducedCosts) {
                if (cost.selected && cost.variable == next.enteringVariable) {
                    selectedEnteringMatches = true;
                }
            }
            if (!selectedEnteringMatches || next.ratioTests.empty()) {
                allGood = false;
            } else {
                const RatioTestEntry* selectedLeaving = nullptr;
                double bestRatio = std::numeric_limits<double>::infinity();
                for (const auto& ratio : next.ratioTests) {
                    if (ratio.eligible) bestRatio = std::min(bestRatio, ratio.ratio);
                    if (ratio.basicVariable == next.leavingVariable) selectedLeaving = &ratio;
                }
                if (!selectedLeaving || !selectedLeaving->eligible ||
                    !close(selectedLeaving->ratio, bestRatio, 1e-6)) {
                    allGood = false;
                } else {
                    ++checkedRatioTests;
                }
            }
        } else if (next.event == "optimal") {
            for (const auto& cost : next.reducedCosts) {
                if (cost.eligible && !cost.artificial) allGood = false;
            }
        }
    }

    const bool hasChecks = checkedPivots > 0 && checkedPivots == checkedReducedCosts;
    check(allGood && hasChecks,
          label + ": each pivot reconstructs the next tableau and agrees with next decision data");
    std::cout << "  " << label << ": pivots verified=" << checkedPivots
              << ", reduced-cost states=" << checkedReducedCosts
              << ", next ratio tests=" << checkedRatioTests << '\n';
    return allGood && hasChecks;
}

LPP standardModel() {
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

LPP mixedModel() {
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
}

int main() {
    std::cout << "=== OptiSolve Next-Iteration Walkthrough Tests ===\n\n";
    const auto simplex = solveSimplex(standardModel());
    const auto twoPhase = solveTwoPhase(mixedModel());
    const auto bigM = solveBigM(mixedModel());

    check(simplex.status == SolveStatus::Optimal,
          "Standard Simplex test model solves optimally");
    check(twoPhase.status == SolveStatus::Optimal,
          "Two-Phase test model solves optimally");
    check(bigM.status == SolveStatus::Optimal,
          "Big-M test model solves optimally");

    verifyMethod("Standard Simplex", simplex);
    verifyMethod("Two-Phase Simplex", twoPhase);
    verifyMethod("Big-M", bigM);

    std::cout << "\nPassed: " << passed << "\nFailed: " << failed << '\n';
    return failed == 0 ? 0 : 1;
}
