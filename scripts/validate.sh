#!/usr/bin/env bash
# Everything that can be checked without an Azure subscription:
#   Bicep build + lint + build-params for every entry point, KQL parse/semantic check, MCP server tests.
set -euo pipefail
cd "$(dirname "$0")/.."
BICEP="${BICEP:-bicep}"
command -v "$BICEP" >/dev/null || BICEP="az bicep"
echo "Bicep: $($BICEP --version)"
for f in infra/main.bicep infra/agent/main.bicep infra/mcp/main.bicep \
         infra/governance/contract-policy.bicep infra/governance/activity-log.bicep infra/governance/audit-alerts.bicep; do
  $BICEP build "$f" --stdout > /dev/null
  $BICEP lint "$f"
  echo "  ok  $f"
done
for p in infra/main.bicepparam infra/agent/main.bicepparam infra/mcp/main.bicepparam; do
  $BICEP build-params "$p" --stdout > /dev/null
  echo "  ok  $p"
done
if [[ -d scripts/kql-check/node_modules ]]; then
  tmp="$(mktemp -d)"
  python3 scripts/kql-check/extract.py "$tmp"
  node scripts/kql-check/check.js queries/*.kql "$tmp"/*.kql
  rm -rf "$tmp"
else
  echo "  skip KQL check (run: cd scripts/kql-check && npm install)"
fi
if [[ -z "${SKIP_PYTEST:-}" ]]; then
  (cd mcp-server && python -m pytest -q)
fi
echo "OK: all checks passed"
