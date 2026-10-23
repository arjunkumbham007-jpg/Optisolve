#pragma once

#include "lpp.h"
#include "simplex.h"
#include <string>

bool exportResultJSON(
    const LPP& model,
    const SimplexResult& result,
    const std::string& filename
);
