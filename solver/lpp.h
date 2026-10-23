#pragma once

#include <string>
#include <vector>

struct Constraint {
    std::vector<double> coefficients;
    std::string relation; // "<=", ">=", or "="
    double rhs;
};

struct LPP {
    bool maximize = true;
    std::vector<double> objective;
    std::vector<Constraint> constraints;
};
