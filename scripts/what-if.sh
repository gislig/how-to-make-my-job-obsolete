#!/usr/bin/env bash
# Preview a change before you apply it.
# Usage: what-if.sh <resource-group> foundation|agent|mcp
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:?usage: what-if.sh <resource-group> foundation|agent|mcp}"
case "${2:-foundation}" in
  foundation) T=infra/main.bicep;       P=infra/main.bicepparam ;;
  agent)      T=infra/agent/main.bicep; P=infra/agent/main.bicepparam ;;
  mcp)        T=infra/mcp/main.bicep;   P=infra/mcp/main.bicepparam ;;
esac
az deployment group what-if --resource-group "$RG" --template-file "$T" --parameters "$P"
