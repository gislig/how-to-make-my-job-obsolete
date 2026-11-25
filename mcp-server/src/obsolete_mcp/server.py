"""The MCP server: read-first tools over one resource group, plus one contract-bounded write.

Transport: Streamable HTTP at /mcp (MCP Python SDK 2.x, MCPServer).
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

from . import __version__, audit
from .analysis import build_timeline, hour_of_week_baseline
from .auth import ApiKeyMiddleware, parse_keys
from .backend import AzureBackend, Backend, utcnow, validate_app_name
from .contract import Contract, ContractError, evaluate_scale_request
from .settings import Settings

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

INSTRUCTIONS = """You are talking to an Azure Container Apps environment through its infrastructure agent.
Start with list_apps or get_status. Every app carries an operating contract (aiops-* tags): a replica envelope,
a change mode (review or autonomous) and a tier. Explain scaling with get_scaling_timeline, compare with
get_baseline, and look at get_recent_changes and get_alerts before you guess. set_scale_range is the only
write: it defaults to dry_run=true, never leaves the contract, and every call is audited. In review mode it
returns a proposal for a human to apply."""


def _client(ctx: Context | None) -> str:
    try:
        state = getattr(ctx.request_context.request, "state", None) if ctx else None
        return getattr(state, "mcp_client", None) or "local"
    except Exception:  # stdio / in-process test client: there is no HTTP request
        return "local"


def build_server(backend: Backend, settings: Settings) -> MCPServer:
    server = MCPServer(name="infra-agent", title="Infrastructure agent", version=__version__, instructions=INSTRUCTIONS)

    async def run(ctx: Context | None, tool: str, args: dict[str, Any], fn, *fargs):
        """Run a blocking backend call off the event loop and audit it."""
        audit.current_client.set(_client(ctx))
        started = time.monotonic()
        try:
            result = await anyio.to_thread.run_sync(fn, *fargs)
            audit.event("McpToolCall", tool=tool, arguments=args, ok=True, ms=int((time.monotonic() - started) * 1000))
            return result
        except Exception as ex:
            audit.event("McpToolCall", tool=tool, arguments=args, ok=False, error=type(ex).__name__,
                        ms=int((time.monotonic() - started) * 1000))
            raise

    def contract_of(app: dict[str, Any]) -> dict[str, Any]:
        try:
            return Contract.from_tags(app["tags"]).to_dict()
        except ContractError as ex:
            return {"error": str(ex)}

    @server.tool(name="list_apps", title="List managed apps", annotations=READ,
                 description="List container apps in the resource group with their current scale range and operating contract.")
    async def list_apps(ctx: Context) -> dict[str, Any]:
        apps = await run(ctx, "list_apps", {}, backend.list_apps)
        return {"resourceGroup": backend.resource_group,
                "apps": [{"name": a["name"], "minReplicas": a["minReplicas"], "maxReplicas": a["maxReplicas"],
                          "runningStatus": a["runningStatus"], "contract": contract_of(a)} for a in apps]}

    @server.tool(name="get_status", title="App status", annotations=READ,
                 description="Current state of one container app: revision, provisioning, scale range, scale rules, "
                             "replica count right now and the operating contract.")
    async def get_status(app: str, ctx: Context) -> dict[str, Any]:
        validate_app_name(app)
        a = await run(ctx, "get_status", {"app": app}, backend.get_app, app)
        end = utcnow()
        series = await run(ctx, "get_status.metrics", {"app": app}, backend.metric_series,
                           a["id"], ["Replicas"], "Maximum", end - timedelta(minutes=15), end, "PT1M")
        points = [v for _, v in series.get("Replicas", []) if v is not None]
        return {**{k: v for k, v in a.items() if k != "tags"}, "replicasNow": points[-1] if points else None,
                "contract": contract_of(a)}

    @server.tool(name="get_contract", title="Operating contract", annotations=READ,
                 description="The operating contract (aiops-* tags) for one app: owner, replica envelope, change mode, tier, SLO, budget.")
    async def get_contract(app: str, ctx: Context) -> dict[str, Any]:
        validate_app_name(app)
        a = await run(ctx, "get_contract", {"app": app}, backend.get_app, app)
        return {"app": app, "contract": contract_of(a), "currentRange": [a["minReplicas"], a["maxReplicas"]]}

    @server.tool(name="get_baseline", title="Hour-of-week baseline", annotations=READ,
                 description="What normal looks like: median and p90 of hourly requests per hour-of-week over the last N days "
                             "(platform metrics), how the last hour compares, and a contract-clipped minReplicas suggestion for the next hour.")
    async def get_baseline(app: str, ctx: Context, days: int = 28) -> dict[str, Any]:
        validate_app_name(app)
        days = max(7, min(days, 90))  # platform metrics are kept 93 days
        a = await run(ctx, "get_baseline", {"app": app, "days": days}, backend.get_app, app)
        c = Contract.from_tags(a["tags"])
        end = utcnow()
        req = await run(ctx, "get_baseline.metrics", {"app": app}, backend.metric_series,
                        a["id"], ["Requests"], "Total", end - timedelta(days=days), end, "PT1H")
        rep = await run(ctx, "get_baseline.metrics", {"app": app}, backend.metric_series,
                        a["id"], ["Replicas"], "Maximum", end - timedelta(days=days), end, "PT1H")
        result = hour_of_week_baseline(req.get("Requests", []), rep.get("Replicas", []), end, c.min_replicas, c.max_replicas)
        return {"app": app, "days": days, **result}

    @server.tool(name="get_scaling_timeline", title="Scaling timeline (and why)", annotations=READ,
                 description="Every replica change in the last N hours with a plain-language reason, merged with configuration "
                             "changes, alerts and agent actions in one ordered timeline.")
    async def get_scaling_timeline(app: str, ctx: Context, hours: int = 24) -> dict[str, Any]:
        validate_app_name(app)
        hours = max(1, min(hours, 24 * 14))  # resourcechanges keeps 14 days
        a = await run(ctx, "get_scaling_timeline", {"app": app, "hours": hours}, backend.get_app, app)
        end = utcnow()
        m = await run(ctx, "get_scaling_timeline.metrics", {"app": app}, backend.metric_series,
                      a["id"], ["Replicas"], "Maximum", end - timedelta(hours=hours), end, "PT1M")
        r = await run(ctx, "get_scaling_timeline.metrics", {"app": app}, backend.metric_series,
                      a["id"], ["Requests"], "Total", end - timedelta(hours=hours), end, "PT1M")
        changes = await run(ctx, "get_scaling_timeline.changes", {"hours": hours}, backend.resource_changes, hours)
        alerts = await run(ctx, "get_scaling_timeline.alerts", {"hours": hours}, backend.alerts, hours)
        events = await run(ctx, "get_scaling_timeline.agent", {"hours": hours}, backend.agent_events, hours)
        timeline = build_timeline(a, m.get("Replicas", []), r.get("Requests", []), changes, alerts, events)
        return {"app": app, "hours": hours, "events": timeline[-200:], "count": len(timeline)}

    @server.tool(name="get_recent_changes", title="What changed", annotations=READ,
                 description="Resource changes in the resource group from Azure Resource Graph (who, what, which client), newest first.")
    async def get_recent_changes(ctx: Context, hours: int = 24) -> dict[str, Any]:
        hours = max(1, min(hours, 24 * 14))
        rows = await run(ctx, "get_recent_changes", {"hours": hours}, backend.resource_changes, hours)
        return {"hours": hours, "changes": rows}

    @server.tool(name="get_alerts", title="Alerts", annotations=READ,
                 description="Azure Monitor alerts for resources in the resource group from Azure Resource Graph, newest first.")
    async def get_alerts(ctx: Context, hours: int = 24) -> dict[str, Any]:
        hours = max(1, min(hours, 24 * 30))
        rows = await run(ctx, "get_alerts", {"hours": hours}, backend.alerts, hours)
        return {"hours": hours, "alerts": rows}

    @server.tool(name="get_agent_activity", title="Agent activity", annotations=READ,
                 description="What the agents did: SRE Agent tool calls, Azure CLI commands and approvals, and this server's own "
                             "audited calls (Application Insights custom events in Log Analytics).")
    async def get_agent_activity(ctx: Context, hours: int = 24) -> dict[str, Any]:
        hours = max(1, min(hours, 24 * 30))
        rows = await run(ctx, "get_agent_activity", {"hours": hours}, backend.agent_events, hours)
        return {"hours": hours, "events": rows, "configured": bool(settings.workspace_id)}

    @server.tool(name="set_scale_range", title="Set scale range (bounded)", annotations=WRITE,
                 description="Change minReplicas/maxReplicas of one app, only inside its operating contract. Defaults to dry_run=true. "
                             "Applies only when the server allows writes AND the contract's effective mode is autonomous; otherwise "
                             "returns a proposal. A reason is required and audited.")
    async def set_scale_range(app: str, min_replicas: int, max_replicas: int, reason: str, ctx: Context,
                              dry_run: bool = True) -> dict[str, Any]:
        validate_app_name(app)
        args = {"app": app, "min": min_replicas, "max": max_replicas, "reason": reason, "dry_run": dry_run}
        a = await run(ctx, "set_scale_range.read", args, backend.get_app, app)
        try:
            c = Contract.from_tags(a["tags"])
        except ContractError as ex:
            audit.event("McpScaleDecision", app=app, decision="rejected", reasons=[str(ex)], **args)
            return {"app": app, "allowed": False, "applied": False, "reasons": [str(ex)]}
        d = evaluate_scale_request(c, a["minReplicas"], a["maxReplicas"], min_replicas, max_replicas, reason,
                                   writes_enabled=settings.allow_writes, dry_run=dry_run, max_step=settings.max_step)
        decision = "applied" if d.apply else ("proposed" if d.allowed else "rejected")
        result: dict[str, Any] = {"app": app, "allowed": d.allowed, "applied": False, "mode": d.mode,
                                  "from": [a["minReplicas"], a["maxReplicas"]], "to": [min_replicas, max_replicas],
                                  "envelope": [c.min_replicas, c.max_replicas], "reasons": d.reasons}
        if d.allowed and not d.apply:
            result["applyCommand"] = (f"az containerapp update -n {app} -g {backend.resource_group} "
                                      f"--min-replicas {min_replicas} --max-replicas {max_replicas}")
        if d.apply:
            after = await run(ctx, "set_scale_range.write", args, backend.set_scale_range, app, min_replicas, max_replicas)
            result.update(applied=True, now=[after["minReplicas"], after["maxReplicas"]], revision=after["latestRevision"])
        audit.event("McpScaleDecision", decision=decision, mode=d.mode, reasons=d.reasons,
                    envelope=[c.min_replicas, c.max_replicas], before=[a["minReplicas"], a["maxReplicas"]], **args)
        return result

    return server


def create_app(settings: Settings | None = None, backend: Backend | None = None):
    """ASGI app: /mcp (Streamable HTTP, API key required) and /healthz (open, for probes)."""
    settings = settings or Settings.from_env()
    keys = parse_keys(settings.api_keys_raw)
    if not keys:
        raise RuntimeError("MCP_API_KEYS is empty; refusing to start an unauthenticated MCP server")
    audit.configure()
    if backend is None:
        if not (settings.subscription_id and settings.resource_group):
            raise RuntimeError("AZURE_SUBSCRIPTION_ID and AIOPS_RESOURCE_GROUP must be set")
        backend = AzureBackend(settings.subscription_id, settings.resource_group, settings.workspace_id)
    server = build_server(backend, settings)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(_request):
        return JSONResponse({"status": "ok", "version": __version__})

    security = None
    if settings.allowed_hosts:
        security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=settings.allowed_hosts,
                                             allowed_origins=[f"https://{h}" for h in settings.allowed_hosts])
    app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                     transport_security=security)
    app.add_middleware(ApiKeyMiddleware, keys=keys)
    return app


def main() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port, proxy_headers=True, forwarded_allow_ips="*")
