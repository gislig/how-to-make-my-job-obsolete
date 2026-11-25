#!/usr/bin/env bash
# Deploy one part of the series as a resource-group deployment stack (Azure CLI 2.61.0 or later).
#   denyDelete: nobody outside the excluded principals can delete what the stack manages, including the agent.
#   detachAll:  removing a resource from the template detaches it instead of deleting it.
# Usage: deploy-stack.sh <resource-group> foundation|agent|mcp [excluded-principal-object-id]
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:?usage: deploy-stack.sh <resource-group> foundation|agent|mcp [excluded-principal-object-id]}"
PART="${2:?part: foundation|agent|mcp}"
EXCLUDED="${3:-}"

case "$PART" in
  foundation) TEMPLATE=infra/main.bicep;       PARAMS=infra/main.bicepparam ;;
  agent)      TEMPLATE=infra/agent/main.bicep; PARAMS=infra/agent/main.bicepparam ;;
  mcp)        TEMPLATE=infra/mcp/main.bicep;   PARAMS=infra/mcp/main.bicepparam ;;
  *) echo "unknown part: $PART" >&2; exit 2 ;;
esac

args=(
  --name "obsolete-$PART"
  --resource-group "$RG"
  --template-file "$TEMPLATE"
  --parameters "$PARAMS"
  --action-on-unmanage detachAll
  --deny-settings-mode denyDelete
  --description "How to Make My Job Obsolete: $PART"
  --yes
)
if [[ -n "$EXCLUDED" ]]; then
  # Exclude a group (recommended), such as your platform team or break-glass admins. Up to five principals.
  args+=(--deny-settings-excluded-principals "$EXCLUDED")
fi
az stack group create "${args[@]}"
