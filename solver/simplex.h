#pragma once

#include "lpp.h"
#include <string>
#include <vector>

enum class SolveStatus {
    Optimal,
    Infeasible,
    Unbounded,
    Unsupported,
    IterationLimit,
    InvalidModel
};

enum class SolveMethod {
    Simplex,
    TwoPhase,
    BigM
};

struct RatioTestEntry {
    std::string basicVariable;
    double rhs = 0.0;
    double enteringCoefficient = 0.0;
    bool eligible = false;
    double ratio = 0.0;
};

struct ReducedCostEntry {
    std::string variable;
    double tableauCoefficient = 0.0; // objective-row coefficient (Z_j - C_j convention)
    bool eligible = false;
    bool selected = false;
    bool artificial = false;
};

struct RowOperation {
    // 1-based tableau row numbers; the objective row is the final row.
    int targetRow = 0;
    int sourceRow = 0;
    // "divide" normalizes the pivot row; "subtract_multiple" eliminates
    // the entering-column coefficient using the normalized pivot row.
    std::string operation;
    double factor = 0.0;
};

struct SolverTraceStep {
    std::string phase;
    std::string event;
    int iteration = 0;
    std::string explanation;
    std::vector<std::string> columnNames;
    std::vector<std::string> basis;
    std::vector<std::vector<double>> tableau;
    bool tableauRecorded = false;
    std::string enteringVariable;
    std::string leavingVariable;
    int pivotRow = -1;       // 1-based constraint row for display
    int pivotColumn = -1;    // 1-based tableau column for display
    double pivotValue = 0.0;
    std::vector<RatioTestEntry> ratioTests;
    std::vector<ReducedCostEntry> reducedCosts;
    std::vector<RowOperation> rowOperations;
};

struct SimplexResult {
    SolveStatus status = SolveStatus::InvalidModel;
    double objectiveValue = 0.0;
    std::vector<double> variableValues;
    int iterations = 0;
    std::string message;
    std::string method = "simplex";
    std::vector<SolverTraceStep> trace;
    bool traceTruncated = false;
};

// Standard Simplex: <= constraints with nonnegative RHS values.
// Supports both maximization and minimization when the initial slack basis
// is feasible. Mixed relations or negative RHS values are not accepted.
SimplexResult solveSimplex(const LPP& model, int maxIterations = 10000);

// Two-Phase Simplex: supports <=, >=, = constraints and negative RHS values.
SimplexResult solveTwoPhase(const LPP& model, int maxIterations = 10000);

// Big-M method: supports <=, >=, = constraints and negative RHS values.
// Uses a finite numerical penalty and is therefore less numerically robust
// than Two-Phase Simplex on badly scaled models.
SimplexResult solveBigM(const LPP& model, int maxIterations = 10000);

SimplexResult solveLPP(
    const LPP& model,
    SolveMethod method,
    int maxIterations = 10000
);

const char* solveMethodName(SolveMethod method);
