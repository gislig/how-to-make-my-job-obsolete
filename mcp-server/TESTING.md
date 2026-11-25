# Test evidence (25 November 2026, GMT)

No Azure subscription was used. Azure is replaced by `tests/fakes.py:FakeBackend`; everything else is the real code.

## Automated

`python -m pytest -q`: **55 passed** (Python 3.13, mcp 2.3.0).

- `test_contract.py`: parsing the `aiops-*` tags, invalid contracts, production is always review, every rejection
  rule in `evaluate_scale_request`, and when a change is applied or proposed.
- `test_analysis.py`: the hour-of-week baseline and its pre-warm suggestion clipped to the contract, replica change
  detection with the load reason, a config change winning over load, and the merged, ordered timeline.
- `test_backend.py`: mapping real `azure-mgmt-appcontainers` 5.1.0 model objects, the sparse scale PATCH body, the query
  builders, and name validation.
- `test_server.py`: every tool through an in-process MCP client, including the write path and its audit events.
- `test_auth.py`: parsing and matching `name:key` pairs, rejecting malformed and short keys, and refusing to start
  without keys.
- `test_http.py`: uvicorn on a real port, an open `/healthz`, 401 without a key or with a wrong key, a rejected
  `Host` header, the Streamable HTTP client with both `Authorization: Bearer` and `X-API-Key`, and the client name in
  the audit log.
- `test_timeline_page.py`: the static HTML page.

`scripts/validate.sh` also builds and lints all Bicep entry points and parses every KQL query (the files in
`queries/`, the queries in the server code and the alert queries in Bicep) against the table schemas.

## MCP Inspector CLI

Server: `ALLOW_WRITES=true PORT=8765 python tests/demo_server.py` (fake backend, one key named `local`).
Client: `npx -y @modelcontextprotocol/inspector@2.16.0 --cli http://127.0.0.1:8765/mcp --transport http
--header "Authorization: Bearer <key>"`, on Node 24.22.1. Raw output is in `evidence/inspector/`.

- `tools/list` (`list.json`): 9 tools: list_apps, get_status, get_contract, get_baseline, get_scaling_timeline,
  get_recent_changes, get_alerts, get_agent_activity, set_scale_range.
- `get_status app=ca-demo-web` (`status.json`): revision `ca-demo-web--r1`, range 1 to 10.
- `set_scale_range` 1 to 50, `dry_run=false` (`reject.json`): `allowed: false`, reasons "new max 50 is above the
  contract ceiling 10" and "change is larger than the per-call step limit of 5 replicas".
- `set_scale_range` 3 to 10, default dry run (`dry.json`): `allowed: true, applied: false`, "dry run: nothing was changed".
- `set_scale_range` 3 to 10, `dry_run=false` (`apply.json`): `applied: true`, new revision `ca-demo-web--r2`.
- `get_scaling_timeline hours=6` (`tl.json`): 4 events (a change, an alert, a scale-out explained by load, an agent tool call).
- Wrong key (`unauth.json`): the server answered `401 Unauthorized` with `WWW-Authenticate: Bearer`. Inspector reports `auth_required`.
- `GET /healthz` without a key: 200.

## Not tested here

Anything that needs Azure: the deployment, managed identity token acquisition, the real Azure APIs, ingestion into
Application Insights, and Grok Bot and SRE Agent connecting over the internet. Do that after `what-if`, starting with
`allowWrites=false`.
