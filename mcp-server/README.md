# obsolete-mcp: the infrastructure agent's MCP server

A remote MCP server (Streamable HTTP, stateless, JSON responses) for one Azure resource group. Part 4 of the series.

## Tools

Read (annotated `readOnlyHint: true`): `list_apps`, `get_status`, `get_contract`, `get_baseline`,
`get_scaling_timeline`, `get_recent_changes`, `get_alerts`, `get_agent_activity`.

Write: `set_scale_range(app, min_replicas, max_replicas, reason, dry_run=true)`. It applies a change only when all of
these hold:

1. The app has a valid operating contract (`aiops-managed=true` and every `aiops-*` tag).
2. The new range is inside the contract, `min <= max`, within `MAX_STEP` of the current values, and has a reason
   of at least 10 characters.
3. `dry_run` is false.
4. The server runs with `ALLOW_WRITES=true`. The Bicep only grants Container Apps Contributor on the target app in that case.
5. The contract's effective mode is autonomous. `aiops-tier=prod` is always review.

Otherwise it returns a proposal with the `az containerapp update` command. The write sends the same sparse PATCH
as `az containerapp update --min-replicas --max-replicas`, so the scale rules are kept.

## Configuration (environment variables)

- `MCP_API_KEYS` (required): `name:key,name:key`. Each key is at least 32 characters. Clients send
  `Authorization: Bearer <key>` or `X-API-Key: <key>`.
- `AZURE_SUBSCRIPTION_ID`, `AIOPS_RESOURCE_GROUP` (required), `LOG_ANALYTICS_WORKSPACE_ID` (workspace GUID).
- `AZURE_CLIENT_ID`: client ID of the user-assigned managed identity.
- `APPLICATIONINSIGHTS_CONNECTION_STRING`: audit events (Entra ID ingestion via the managed identity).
- `MCP_ALLOWED_HOSTS`: host names accepted in the `Host` header (DNS-rebinding protection).
- `ALLOW_WRITES` (default `false`), `MAX_STEP` (default `5`), `PORT` (default `8000`).

Endpoints: `POST /mcp` (MCP), `GET /healthz` (no auth, liveness probe).

## Run the tests

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
python -m pytest -q
```

## Run locally against fake data

```bash
export MCP_API_KEYS="local:$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
ALLOW_WRITES=true PORT=8765 python tests/demo_server.py
npx -y @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:8765/mcp --transport http \
  --header "Authorization: Bearer ${MCP_API_KEYS#local:}" --method tools/list
```

## Timeline page

```bash
python -m obsolete_mcp.timeline_page --subscription <id> --resource-group <rg> --app <app> \
  --workspace-id <workspace-guid> --hours 24 --out timeline.html
```

Uses your Azure CLI login (`DefaultAzureCredential`).

## Deploy

`../scripts/deploy-mcp.sh <resource-group> [image-tag]`. See `../infra/mcp/main.bicep` and `TESTING.md`.
