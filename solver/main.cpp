#include <bits/stdc++.h>
#include "json_export.h"
#include "lpp.h"
#include "simplex.h"

using namespace std;

void printExpression(const vector<double>& coefficients) {
    bool first = true;
    for (int i = 0; i < static_cast<int>(coefficients.size()); ++i) {
        const double value = coefficients[i];
        if (value == 0.0) continue;
        if (!first) cout << (value < 0 ? " - " : " + ");
        else if (value < 0) cout << "-";
        cout << abs(value) << "*x" << i + 1;
        first = false;
    }
    if (first) cout << "0";
}

bool parseMethod(int argc, char* argv[], SolveMethod& method) {
    method = SolveMethod::Simplex;
    if (argc == 1) return true;
    if (argc != 3 || string(argv[1]) != "--algorithm") return false;

    const string name = argv[2];
    if (name == "simplex") method = SolveMethod::Simplex;
    else if (name == "two-phase" || name == "two_phase") method = SolveMethod::TwoPhase;
    else if (name == "big-m" || name == "big_m") method = SolveMethod::BigM;
    else return false;
    return true;
}

int main(int argc, char* argv[]) {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    SolveMethod method;
    if (!parseMethod(argc, argv, method)) {
        cerr << "Usage: optisolve [--algorithm simplex|two-phase|big-m]\n";
        return 2;
    }

    LPP model;
    string type;
    int n = 0, m = 0;

    cout << "=== OptiSolve: LPP Model Builder ===\n\n";
    cout << "Enter optimization type (max/min): ";
    if (!(cin >> type)) {
        cerr << "Missing optimization type.\n";
        return 1;
    }
    for (char& c : type) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
    if (type != "max" && type != "min") {
        cerr << "Invalid optimization type.\n";
        return 1;
    }
    model.maximize = (type == "max");

    cout << "Enter number of variables: ";
    if (!(cin >> n)) return 1;
    cout << "Enter number of constraints: ";
    if (!(cin >> m)) return 1;
    if (n < 1 || m < 1 || n > 100 || m > 500) {
        cerr << "Invalid number of variables or constraints (limits: 100 variables, 500 constraints).\n";
        return 1;
    }

    model.objective.resize(n);
    model.constraints.resize(m);
    cout << "\nEnter the " << n << " objective coefficients:\n";
    for (double& coefficient : model.objective) {
        if (!(cin >> coefficient) || !isfinite(coefficient)) {
            cerr << "Invalid objective coefficient.\n";
            return 1;
        }
    }

    for (int i = 0; i < m; ++i) {
        cout << "\nConstraint " << i + 1 << "\n";
        cout << "Enter " << n << " coefficients, relation (<=, >=, =), and RHS:\n";
        Constraint& constraint = model.constraints[i];
        constraint.coefficients.resize(n);
        for (double& coefficient : constraint.coefficients) {
            if (!(cin >> coefficient) || !isfinite(coefficient)) {
                cerr << "Invalid constraint coefficient.\n";
                return 1;
            }
        }
        if (!(cin >> constraint.relation >> constraint.rhs) || !isfinite(constraint.rhs)) {
            cerr << "Invalid relation or right-hand side.\n";
            return 1;
        }
        if (constraint.relation != "<=" && constraint.relation != ">=" && constraint.relation != "=") {
            cerr << "Invalid constraint relation. Use <=, >=, or =.\n";
            return 1;
        }
    }

    cout << "\n========== YOUR LPP MODEL ==========\n\n";
    cout << (model.maximize ? "Maximize" : "Minimize") << " Z = ";
    printExpression(model.objective);
    cout << "\n\nSubject to:\n";
    for (const auto& constraint : model.constraints) {
        printExpression(constraint.coefficients);
        cout << " " << constraint.relation << " " << constraint.rhs << "\n";
    }
    cout << "\nNon-negativity restrictions:\n";
    for (int i = 0; i < n; ++i) cout << "x" << i + 1 << " >= 0\n";
    cout << "\nSelected algorithm: " << solveMethodName(method) << "\n";
    cout << "Model created successfully.\n";

    SimplexResult result = solveLPP(model, method);
    cout << "\n========== OPTIMIZATION RESULT ==========\n";
    cout << result.message << "\n";
    cout << "Status: ";
    switch (result.status) {
        case SolveStatus::Optimal: cout << "optimal"; break;
        case SolveStatus::Infeasible: cout << "infeasible"; break;
        case SolveStatus::Unbounded: cout << "unbounded"; break;
        case SolveStatus::Unsupported: cout << "unsupported"; break;
        case SolveStatus::IterationLimit: cout << "iteration limit"; break;
        case SolveStatus::InvalidModel: cout << "invalid model"; break;
    }
    cout << "\nIterations: " << result.iterations << "\n";

    if (result.status == SolveStatus::Optimal) {
        cout << setprecision(10);
        cout << "Optimal objective value: " << result.objectiveValue << "\n";
        cout << "Optimal variable values:\n";
        for (int i = 0; i < static_cast<int>(result.variableValues.size()); ++i) {
            cout << "x" << i + 1 << " = " << result.variableValues[i] << "\n";
        }
    }

    if (exportResultJSON(model, result, "optisolve_result.json")) {
        cout << "\nJSON result saved to optisolve_result.json\n";
    } else {
        cerr << "\nFailed to write JSON result.\n";
    }
    return 0;
}
