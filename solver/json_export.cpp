#include "json_export.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <string>

namespace {

std::string escapeJSON(const std::string& text) {
    std::string result;
    const char* hex = "0123456789abcdef";

    for (unsigned char c : text) {
        switch (c) {
            case '"':  result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\b': result += "\\b";  break;
            case '\f': result += "\\f";  break;
            case '\n': result += "\\n";  break;
            case '\r': result += "\\r";  break;
            case '\t': result += "\\t";  break;
            default:
                if (c < 0x20) {
                    result += "\\u00";
                    result += hex[(c >> 4) & 0x0f];
                    result += hex[c & 0x0f];
                } else {
                    result += static_cast<char>(c);
                }
        }
    }
    return result;
}

const char* statusName(SolveStatus status) {
    switch (status) {
        case SolveStatus::Optimal:        return "optimal";
        case SolveStatus::Infeasible:     return "infeasible";
        case SolveStatus::Unbounded:      return "unbounded";
        case SolveStatus::Unsupported:    return "unsupported";
        case SolveStatus::IterationLimit: return "iteration_limit";
        case SolveStatus::InvalidModel:   return "invalid_model";
    }
    return "unknown";
}

void writeNumber(std::ostream& out, double value) {
    if (std::isfinite(value)) out << std::setprecision(17) << value;
    else out << "null";
}

void writeNumberArray(std::ostream& out, const std::vector<double>& values) {
    out << "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) out << ", ";
        writeNumber(out, values[i]);
    }
    out << "]";
}

void writeStringArray(std::ostream& out, const std::vector<std::string>& values) {
    out << "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) out << ", ";
        out << "\"" << escapeJSON(values[i]) << "\"";
    }
    out << "]";
}

void writeTableau(
    std::ostream& out,
    const std::vector<std::vector<double>>& tableau
) {
    out << "[";
    for (std::size_t i = 0; i < tableau.size(); ++i) {
        if (i > 0) out << ", ";
        writeNumberArray(out, tableau[i]);
    }
    out << "]";
}

}

bool exportResultJSON(
    const LPP& model,
    const SimplexResult& result,
    const std::string& filename
) {
    std::ofstream out(filename);
    if (!out) return false;

    out << "{\n";
    out << "  \"schema_version\": 1,\n";
    out << "  \"status\": \"" << statusName(result.status) << "\",\n";
    out << "  \"method\": \"" << escapeJSON(result.method) << "\",\n";
    out << "  \"message\": \"" << escapeJSON(result.message) << "\",\n";
    out << "  \"iterations\": " << result.iterations << ",\n";

    out << "  \"model\": {\n";
    out << "    \"sense\": \"" << (model.maximize ? "maximize" : "minimize") << "\",\n";
    out << "    \"variable_names\": [";
    for (std::size_t i = 0; i < model.objective.size(); ++i) {
        if (i > 0) out << ", ";
        out << "\"x" << i + 1 << "\"";
    }
    out << "],\n";
    out << "    \"objective_coefficients\": ";
    writeNumberArray(out, model.objective);
    out << ",\n";
    out << "    \"nonnegative_variables\": true,\n";
    out << "    \"constraints\": [\n";

    for (std::size_t i = 0; i < model.constraints.size(); ++i) {
        const Constraint& constraint = model.constraints[i];
        out << "      {\n";
        out << "        \"coefficients\": ";
        writeNumberArray(out, constraint.coefficients);
        out << ",\n";
        out << "        \"relation\": \"" << escapeJSON(constraint.relation) << "\",\n";
        out << "        \"rhs\": ";
        writeNumber(out, constraint.rhs);
        out << "\n      }" << (i + 1 < model.constraints.size() ? "," : "") << "\n";
    }

    out << "    ]\n  },\n";
    if (result.status == SolveStatus::Optimal) {
        out << "  \"solution\": {\n";
        out << "    \"objective_value\": ";
        writeNumber(out, result.objectiveValue);
        out << ",\n    \"variables\": ";
        writeNumberArray(out, result.variableValues);
        out << "\n  },\n";
    } else {
        out << "  \"solution\": null,\n";
    }

    out << "  \"trace_truncated\": " << (result.traceTruncated ? "true" : "false") << ",\n";
    out << "  \"trace\": [\n";
    for (std::size_t i = 0; i < result.trace.size(); ++i) {
        const SolverTraceStep& step = result.trace[i];
        out << "    {\n";
        out << "      \"phase\": \"" << escapeJSON(step.phase) << "\",\n";
        out << "      \"event\": \"" << escapeJSON(step.event) << "\",\n";
        out << "      \"iteration\": " << step.iteration << ",\n";
        out << "      \"explanation\": \"" << escapeJSON(step.explanation) << "\",\n";
        out << "      \"column_names\": ";
        writeStringArray(out, step.columnNames);
        out << ",\n      \"basis\": ";
        writeStringArray(out, step.basis);
        out << ",\n      \"tableau_recorded\": " << (step.tableauRecorded ? "true" : "false") << ",\n";
        out << "      \"tableau\": ";
        if (step.tableauRecorded) writeTableau(out, step.tableau);
        else out << "null";
        out << ",\n      \"entering_variable\": ";
        if (step.enteringVariable.empty()) out << "null";
        else out << "\"" << escapeJSON(step.enteringVariable) << "\"";
        out << ",\n      \"leaving_variable\": ";
        if (step.leavingVariable.empty()) out << "null";
        else out << "\"" << escapeJSON(step.leavingVariable) << "\"";
        out << ",\n      \"pivot_row\": ";
        if (step.pivotRow < 0) out << "null";
        else out << step.pivotRow;
        out << ",\n      \"pivot_column\": ";
        if (step.pivotColumn < 0) out << "null";
        else out << step.pivotColumn;
        out << ",\n      \"pivot_value\": ";
        if (step.enteringVariable.empty() || step.leavingVariable.empty()) out << "null";
        else writeNumber(out, step.pivotValue);
        out << ",\n      \"ratio_tests\": [";
        for (std::size_t r = 0; r < step.ratioTests.size(); ++r) {
            const RatioTestEntry& candidate = step.ratioTests[r];
            if (r > 0) out << ", ";
            out << "{\"basic_variable\": \"" << escapeJSON(candidate.basicVariable) << "\", ";
            out << "\"rhs\": ";
            writeNumber(out, candidate.rhs);
            out << ", \"entering_coefficient\": ";
            writeNumber(out, candidate.enteringCoefficient);
            out << ", \"eligible\": " << (candidate.eligible ? "true" : "false");
            out << ", \"ratio\": ";
            if (candidate.eligible) writeNumber(out, candidate.ratio);
            else out << "null";
            out << "}";
        }
        out << "],\n      \"reduced_costs\": [";
        for (std::size_t r = 0; r < step.reducedCosts.size(); ++r) {
            const ReducedCostEntry& candidate = step.reducedCosts[r];
            if (r > 0) out << ", ";
            out << "{\"variable\": \"" << escapeJSON(candidate.variable) << "\", ";
            out << "\"tableau_coefficient\": ";
            writeNumber(out, candidate.tableauCoefficient);
            out << ", \"eligible\": " << (candidate.eligible ? "true" : "false");
            out << ", \"selected\": " << (candidate.selected ? "true" : "false");
            out << ", \"artificial\": " << (candidate.artificial ? "true" : "false") << "}";
        }
        out << "],\n      \"row_operations\": [";
        for (std::size_t r = 0; r < step.rowOperations.size(); ++r) {
            const RowOperation& operation = step.rowOperations[r];
            if (r > 0) out << ", ";
            out << "{\"target_row\": " << operation.targetRow
                << ", \"source_row\": " << operation.sourceRow
                << ", \"operation\": \"" << escapeJSON(operation.operation) << "\", \"factor\": ";
            writeNumber(out, operation.factor);
            out << "}";
        }
        out << "]\n    }" << (i + 1 < result.trace.size() ? "," : "") << "\n";
    }
    out << "  ]\n";
    out << "}\n";
    out.close();
    return out.good();
}
