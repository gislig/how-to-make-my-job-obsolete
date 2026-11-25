#!/usr/bin/env bash
# Preview the change before the stack applies it. The agent will use the same command later in the series.
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:?usage: what-if.sh <resource-group>}"
az deployment group what-if \
  --resource-group "$RG" \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
