#!/usr/bin/env bash
# Part 3: contract policy (subscription), Activity Log export (subscription), audit alerts (resource group).
# Usage: deploy-governance.sh <resource-group> <prefix> <location> [Audit|Deny]
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:?usage: deploy-governance.sh <resource-group> <prefix> <location> [Audit|Deny]}"
PREFIX="${2:?prefix, same as part 1}"
LOC="${3:?location}"
EFFECT="${4:-Audit}"
WS_ID=$(az monitor log-analytics workspace show -g "$RG" -n "log-${PREFIX}" --query id -o tsv)
AG_ID=$(az monitor action-group show -g "$RG" -n "ag-${PREFIX}" --query id -o tsv)

az deployment sub create -l "$LOC" -f infra/governance/contract-policy.bicep \
  -p effect="$EFFECT" resourceGroupName="$RG"
az deployment sub create -l "$LOC" -f infra/governance/activity-log.bicep -p workspaceId="$WS_ID"
az deployment group create -g "$RG" -f infra/governance/audit-alerts.bicep \
  -p prefix="$PREFIX" workspaceId="$WS_ID" actionGroupId="$AG_ID"
