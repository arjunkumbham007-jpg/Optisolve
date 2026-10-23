#include "../solver/lpp.h"
#include "../solver/simplex.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <random>
#include <string>
#include <vector>

static bool near(double a, double b, double tol=1e-5) { return std::abs(a-b) <= tol * (1.0 + std::max(std::abs(a), std::abs(b))); }
static bool feasible(const LPP& model, const SimplexResult& r, double eps=1e-5) {
    if (r.status != SolveStatus::Optimal || r.variableValues.size()!=model.objective.size()) return false;
    for (double x : r.variableValues) if (x < -eps || !std::isfinite(x)) return false;
    for (const auto& c : model.constraints) {
        double lhs=0; for (std::size_t j=0;j<c.coefficients.size();++j) lhs += c.coefficients[j]*r.variableValues[j];
        if (c.relation=="<=" && lhs > c.rhs+eps) return false;
        if (c.relation==">=" && lhs < c.rhs-eps) return false;
        if (c.relation=="=" && std::abs(lhs-c.rhs)>eps) return false;
    }
    double z=0; for (std::size_t j=0;j<model.objective.size();++j) z += model.objective[j]*r.variableValues[j];
    return near(z,r.objectiveValue);
}
int main() {
    std::mt19937 rng(19771023);
    std::uniform_int_distribution<int> nDist(1,4), capDist(2,10), cDist(-5,5), aDist(-4,4), marginDist(0,4), relDist(0,2), boolDist(0,1);
    int mixedCount=0, simpleCount=0;
    for (int t=0; t<1000; ++t) {
        const int n=nDist(rng);
        LPP model; model.maximize=boolDist(rng); model.objective.resize(n);
        for (double& c : model.objective) c=cDist(rng);
        std::vector<int> caps(n), p(n);
        for (int j=0;j<n;++j) { caps[j]=capDist(rng); std::uniform_int_distribution<int> pd(0,caps[j]); p[j]=pd(rng); }
        for (int j=0;j<n;++j) { std::vector<double> a(n,0); a[j]=1; model.constraints.push_back({a,"<=",static_cast<double>(caps[j])}); }
        bool pureLE = (t%2==0);
        for (int k=0;k<4;++k) {
            std::vector<double> a(n); bool nonzero=false; double dot=0;
            for (int j=0;j<n;++j) { a[j]=aDist(rng); dot += a[j]*p[j]; nonzero |= (a[j]!=0); }
            if (!nonzero) a[0]=1, dot=p[0];
            if (pureLE) {
                double rhs=std::max(0.0,dot)+marginDist(rng);
                model.constraints.push_back({a,"<=",rhs});
            } else {
                int rel=relDist(rng); std::string relation=rel==0?"<=":(rel==1?">=":"=");
                double rhs=dot;
                if (relation=="<=") rhs += marginDist(rng);
                if (relation==">=") rhs -= marginDist(rng);
                model.constraints.push_back({a,relation,rhs});
            }
        }
        auto tp=solveTwoPhase(model,5000);
        auto bm=solveBigM(model,5000);
        if (!feasible(model,tp) || !feasible(model,bm) || tp.status != bm.status || !near(tp.objectiveValue,bm.objectiveValue,5e-5)) {
            std::cerr << "FAIL mixed idx=" << t << " n=" << n << " sense=" << model.maximize << " TP=" << (int)tp.status << " BM=" << (int)bm.status << " zTP=" << tp.objectiveValue << " zBM=" << bm.objectiveValue << "\n";
            std::cerr << "objective:"; for(double c:model.objective) std::cerr << " " << c; std::cerr << "\n";
            for(const auto& con:model.constraints){ for(double a:con.coefficients) std::cerr << a << " "; std::cerr << con.relation << " " << con.rhs << "\n"; }
            std::cerr << "TP vars:"; for(double x:tp.variableValues) std::cerr << " " << x; std::cerr << "\nBM vars:"; for(double x:bm.variableValues) std::cerr << " " << x; std::cerr << "\n";
            std::cerr << "TP msg: " << tp.message << "\nBM msg: " << bm.message << "\n";
            return 1;
        }
        ++mixedCount;
        if (pureLE) {
            auto sm=solveSimplex(model,5000);
            if (!feasible(model,sm) || sm.status!=tp.status || !near(sm.objectiveValue,tp.objectiveValue,5e-5)) {
                std::cerr << "FAIL simplex idx=" << t << " n=" << n << " sense=" << model.maximize << " S=" << (int)sm.status << " TP=" << (int)tp.status << " zS=" << sm.objectiveValue << " zTP=" << tp.objectiveValue << "\n";
                return 2;
            }
            ++simpleCount;
        }
    }
    std::cout << "Randomized consistency passed: " << mixedCount << " mixed-method models across Two-Phase and Big-M; " << simpleCount << " <=-only models also matched Standard Simplex.\n";
    return 0;
}
