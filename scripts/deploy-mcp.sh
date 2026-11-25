#!/usr/bin/env bash
# Part 4: build and deploy the MCP server. Prints the URL and the API keys ONCE. Store them in your password manager.
# Usage: deploy-mcp.sh <resource-group> [image-tag]
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:?usage: deploy-mcp.sh <resource-group> [image-tag]}"
export IMAGE_TAG="${2:-1.0.0}"

# One key per client, so each can be rotated on its own and the audit log shows who called.
GROK_KEY=$(openssl rand -base64 36 | tr -d '/+=' )
SRE_KEY=$(openssl rand -base64 36 | tr -d '/+=' )
export MCP_API_KEYS="grokbot:${GROK_KEY},sre-agent:${SRE_KEY}"

echo "Step 1/3: registry, identity, roles"
DEPLOY_APP=false ./scripts/deploy-stack.sh "$RG" mcp
ACR=$(az acr list -g "$RG" --query "[0].name" -o tsv)

echo "Step 2/3: build the image in Azure"
az acr build -r "$ACR" -t "infra-agent-mcp:${IMAGE_TAG}" mcp-server

echo "Step 3/3: the container app"
DEPLOY_APP=true ./scripts/deploy-stack.sh "$RG" mcp
URL=$(az containerapp show -g "$RG" -n "$(az containerapp list -g "$RG" --query "[?ends_with(name,'-mcp')].name | [0]" -o tsv)" \
  --query properties.configuration.ingress.fqdn -o tsv)

cat <<OUT

MCP endpoint : https://${URL}/mcp
Grok Bot key : ${GROK_KEY}
SRE Agent key: ${SRE_KEY}
Header       : Authorization: Bearer <key>   (or X-API-Key: <key>)
OUT
