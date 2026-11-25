#!/usr/bin/env bash
# Deploy the foundation as a resource-group deployment stack.
#   denyDelete: nobody (outside the excluded principals) can delete what the stack manages.
#   Writes are still allowed in part 2, because the agent will tune scale settings later in the series.
#   detachAll: removing a resource from the template detaches it instead of deleting it. Safe default while you learn.
# Requires Azure CLI 2.61.0 or later.
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:?usage: deploy-stack.sh <resource-group> [excluded-principal-object-id]}"
EXCLUDED="${2:-}"

args=(
  --name "aiops-foundation"
  --resource-group "$RG"
  --template-file infra/main.bicep
  --parameters infra/main.bicepparam
  --action-on-unmanage detachAll
  --deny-settings-mode denyDelete
  --description "AI ops agent series: monitoring baseline and sample workload"
  --yes
)
if [[ -n "$EXCLUDED" ]]; then
  # Exclude a group (recommended) such as your platform team or break-glass admins. Max five principals.
  args+=(--deny-settings-excluded-principals "$EXCLUDED")
fi

az stack group create "${args[@]}"
