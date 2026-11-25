#!/usr/bin/env bash
# Build and lint every Bicep entry point. Exit code is non-zero on any error.
set -euo pipefail
cd "$(dirname "$0")/.."
BICEP="${BICEP:-bicep}"
command -v "$BICEP" >/dev/null || BICEP="az bicep"
echo "Bicep: $($BICEP --version)"
$BICEP build infra/main.bicep --stdout > /dev/null
$BICEP lint infra/main.bicep
$BICEP build-params infra/main.bicepparam --stdout > /dev/null
echo "OK: build, lint and build-params passed"
