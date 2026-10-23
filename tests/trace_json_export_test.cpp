#include "../solver/lpp.h"
#include "../solver/simplex.h"
#include "../solver/json_export.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

int main() {
    LPP model;
    model.maximize = true;
    model.objective = {4, 3};
    model.constraints = {
        {{1, 1}, "<=", 4},
        {{1, 0}, "<=", 2},
        {{0, 1}, "<=", 3}
    };

    const SimplexResult result = solveSimplex(model);
    if (result.status != SolveStatus::Optimal) {
        std::cerr << "Expected an optimal result.\n";
        return 1;
    }

    const bool pivotHasRatios = [&]() {
        for (const auto& step : result.trace) {
            if (step.event == "pivot") return !step.ratioTests.empty();
        }
        return false;
    }();

    if (!pivotHasRatios) {
        std::cerr << "Pivot trace did not include ratio candidates.\n";
        return 1;
    }

    const bool pivotHasReducedCosts = [&]() {
        for (const auto& step : result.trace) {
            if (step.event == "pivot") {
                return !step.reducedCosts.empty() &&
                    step.reducedCosts.front().variable == "x1" &&
                    step.reducedCosts.front().selected;
            }
        }
        return false;
    }();
    if (!pivotHasReducedCosts) {
        std::cerr << "Pivot trace did not include reduced-cost / entering-candidate data.\n";
        return 1;
    }

    const bool pivotHasRowOperations = [&]() {
        for (const auto& step : result.trace) {
            if (step.event == "pivot") {
                bool divide = false;
                bool eliminate = false;
                for (const auto& operation : step.rowOperations) {
                    divide = divide || operation.operation == "divide";
                    eliminate = eliminate || operation.operation == "subtract_multiple";
                }
                return divide && eliminate;
            }
        }
        return false;
    }();
    if (!pivotHasRowOperations) {
        std::cerr << "Pivot trace did not include row operations.\n";
        return 1;
    }

    if (!exportResultJSON(model, result, "/tmp/optisolve_ratio_trace.json")) {
        std::cerr << "Failed to export result JSON.\n";
        return 1;
    }

    std::ifstream input("/tmp/optisolve_ratio_trace.json");
    const std::string json((std::istreambuf_iterator<char>(input)),
                           std::istreambuf_iterator<char>());
    if (json.find("\"row_operations\"") == std::string::npos ||
        json.find("\"operation\": \"divide\"") == std::string::npos ||
        json.find("\"operation\": \"subtract_multiple\"") == std::string::npos) {
        std::cerr << "Exported JSON did not include expected row operations.\n";
        return 1;
    }

    std::cout << "Ratio and row-operation trace JSON exported.\n";
    return 0;
}
