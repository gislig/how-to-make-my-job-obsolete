"""Everything that talks to Azure lives here, behind a small interface so the tools can be tested offline.

Data sources (all documented, see part4/verification.md):
- Container app config and tags: Microsoft.App/containerApps GET (azure-mgmt-appcontainers).
- Replica count and request volume: Azure Monitor platform metrics `Replicas` and `Requests` (azure-mgmt-monitor).
- What changed: Azure Resource Graph `resourcechanges` table.
- Alerts: Azure Resource Graph `alertsmanagementresources` table.
- What the agents did: Log Analytics `AppEvents` (workspace-based Application Insights customEvents).
- Scale writes: the same sparse PATCH body `az containerapp update --min-replicas --max-replicas` sends.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}[a-z0-9]$")  # container app names: lowercase, digits, hyphens
RG_RE = re.compile(r"^[-\w._()]{1,90}$")


class Backend(Protocol):
    resource_group: str

    def list_apps(self) -> list[dict[str, Any]]: ...
    def get_app(self, name: str) -> dict[str, Any]: ...
    def metric_series(
        self, resource_id: str, metrics: list[str], aggregation: str, start: datetime, end: datetime, interval: str
    ) -> dict[str, list[tuple[datetime, float | None]]]: ...
    def resource_changes(self, hours: int) -> list[dict[str, Any]]: ...
    def alerts(self, hours: int) -> list[dict[str, Any]]: ...
    def agent_events(self, hours: int) -> list[dict[str, Any]]: ...
    def set_scale_range(self, name: str, min_replicas: int, max_replicas: int) -> dict[str, Any]: ...


def validate_app_name(name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise ValueError(f"invalid container app name: {name!r}")
    return name


def app_summary(app: Any) -> dict[str, Any]:
    """Flatten an azure-mgmt-appcontainers ContainerApp model (5.x, properties nested) into plain JSON."""
    props = app.properties
    template = props.template if props else None
    scale = template.scale if template else None
    rules = []
    for r in (scale.rules or []) if scale else []:
        if r.custom is not None:
            kind, metadata = "custom", {"scaler": r.custom.type, **dict(r.custom.metadata or {})}
        elif r.http is not None:
            kind, metadata = "http", dict(r.http.metadata or {})
        elif r.tcp is not None:
            kind, metadata = "tcp", dict(r.tcp.metadata or {})
        elif r.azure_queue is not None:
            kind, metadata = "azureQueue", {}
        else:
            kind, metadata = "unknown", {}
        rules.append({"name": r.name, "kind": kind, "metadata": metadata})
    config = props.configuration if props else None
    ingress = config.ingress if config else None

    def s(v):
        return None if v is None else str(getattr(v, "value", v))

    return {
        "id": app.id,
        "name": app.name,
        "location": app.location,
        "tags": dict(app.tags or {}),
        "provisioningState": s(props.provisioning_state) if props else None,
        "runningStatus": s(props.running_status) if props else None,
        "latestRevision": props.latest_revision_name if props else None,
        "latestReadyRevision": props.latest_ready_revision_name if props else None,
        "fqdn": ingress.fqdn if ingress else None,
        "minReplicas": scale.min_replicas if scale else None,
        "maxReplicas": scale.max_replicas if scale else None,
        "scaleRules": rules,
    }


def resource_changes_query(resource_group: str, hours: int) -> str:
    # Shape from https://learn.microsoft.com/azure/governance/resource-graph/how-to/get-resource-changes
    return f"""resourcechanges
| extend changeTime = todatetime(properties.changeAttributes.timestamp),
    targetResourceId = tostring(properties.targetResourceId),
    changeType = tostring(properties.changeType),
    changedBy = tostring(properties.changeAttributes.changedBy),
    clientType = tostring(properties.changeAttributes.clientType),
    operation = tostring(properties.changeAttributes.operation),
    changes = properties.changes
| where changeTime > ago({int(hours)}h)
| where targetResourceId contains '/resourceGroups/{resource_group}/'
| project changeTime, targetResourceId, changeType, changedBy, clientType, operation, changes
| order by changeTime desc
| take 200"""


def alerts_query(resource_group: str, hours: int) -> str:
    # Field names from https://learn.microsoft.com/azure/azure-monitor/fundamentals/resource-graph-samples
    return f"""alertsmanagementresources
| extend startTime = todatetime(properties.essentials.startDateTime),
    monitorCondition = tostring(properties.essentials.monitorCondition),
    severity = tostring(properties.essentials.severity),
    alertRule = tostring(properties.essentials.alertRule),
    targetResource = tostring(properties.essentials.targetResource)
| where startTime > ago({int(hours)}h)
| where targetResource contains '/resourceGroups/{resource_group}/'
| project startTime, name, severity, monitorCondition, alertRule, targetResource
| order by startTime desc
| take 200"""


AGENT_EVENT_NAMES = ("AgentToolExecution", "AgentAzCliExecution", "ApprovalDecision", "McpToolCall", "McpScaleDecision")


def agent_events_query(hours: int) -> str:
    names = ", ".join(f'"{n}"' for n in AGENT_EVENT_NAMES)
    return f"""AppEvents
| where TimeGenerated > ago({int(hours)}h)
| where Name in ({names})
| project TimeGenerated, Name, AppRoleName, Properties
| order by TimeGenerated desc
| take 300"""


def sparse_scale_patch(min_replicas: int, max_replicas: int) -> dict[str, Any]:
    """Same body as `az containerapp update --min-replicas --max-replicas` (Azure CLI 2.91.0, custom.py):
    only template.scale min/max, rules left out so the existing scale rules are kept."""
    return {"properties": {"template": {"scale": {"minReplicas": min_replicas, "maxReplicas": max_replicas}}}}


@dataclass
class AzureBackend:
    subscription_id: str
    resource_group: str
    workspace_id: str | None = None  # Log Analytics workspace (customer) ID, a GUID

    def __post_init__(self) -> None:
        if not RG_RE.match(self.resource_group):
            raise ValueError("invalid resource group name")
        from azure.identity import DefaultAzureCredential  # uses AZURE_CLIENT_ID for a user-assigned identity

        self._cred = DefaultAzureCredential()
        self._apps = None
        self._monitor = None
        self._graph = None
        self._logs = None

    # --- clients, created lazily so the server starts even if one service is unreachable
    @property
    def apps(self):
        if self._apps is None:
            from azure.mgmt.appcontainers import ContainerAppsAPIClient

            self._apps = ContainerAppsAPIClient(self._cred, self.subscription_id)
        return self._apps

    @property
    def monitor(self):
        if self._monitor is None:
            from azure.mgmt.monitor import MonitorManagementClient

            self._monitor = MonitorManagementClient(self._cred, self.subscription_id)
        return self._monitor

    @property
    def graph(self):
        if self._graph is None:
            from azure.mgmt.resourcegraph import ResourceGraphClient

            self._graph = ResourceGraphClient(self._cred)
        return self._graph

    @property
    def logs(self):
        if self._logs is None:
            from azure.monitor.query import LogsQueryClient

            self._logs = LogsQueryClient(self._cred)
        return self._logs

    # --- reads
    def list_apps(self) -> list[dict[str, Any]]:
        return [app_summary(a) for a in self.apps.container_apps.list_by_resource_group(self.resource_group)]

    def get_app(self, name: str) -> dict[str, Any]:
        return app_summary(self.apps.container_apps.get(self.resource_group, validate_app_name(name)))

    def metric_series(self, resource_id, metrics, aggregation, start, end, interval):
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        resp = self.monitor.metrics.list(
            resource_id,
            timespan=f"{start.astimezone(timezone.utc).strftime(fmt)}/{end.astimezone(timezone.utc).strftime(fmt)}",
            interval=interval,
            metricnames=",".join(metrics),
            aggregation=aggregation,
        )
        out: dict[str, list[tuple[datetime, float | None]]] = {}
        attr = aggregation.lower()
        for m in resp.value:
            points = []
            for ts in m.timeseries or []:
                for d in ts.data or []:
                    points.append((d.time_stamp, getattr(d, attr, None)))
            out[m.name.value] = points
        return out

    def _graph_rows(self, query: str) -> list[dict[str, Any]]:
        from azure.mgmt.resourcegraph.models import QueryRequest

        return list(self.graph.resources(QueryRequest(query=query, subscriptions=[self.subscription_id])).data)

    def resource_changes(self, hours: int) -> list[dict[str, Any]]:
        return self._graph_rows(resource_changes_query(self.resource_group, hours))

    def alerts(self, hours: int) -> list[dict[str, Any]]:
        return self._graph_rows(alerts_query(self.resource_group, hours))

    def agent_events(self, hours: int) -> list[dict[str, Any]]:
        if not self.workspace_id:
            return []
        from azure.monitor.query import LogsQueryStatus

        res = self.logs.query_workspace(self.workspace_id, agent_events_query(hours), timespan=timedelta(hours=hours))
        tables = res.tables if res.status == LogsQueryStatus.SUCCESS else (res.partial_data or [])
        rows = []
        for table in tables:
            cols = list(table.columns)
            for r in table.rows:
                row = dict(zip(cols, list(r)))
                if isinstance(row.get("Properties"), str):
                    try:
                        row["Properties"] = json.loads(row["Properties"])
                    except ValueError:
                        pass
                rows.append(row)
        return rows

    # --- the one write
    def set_scale_range(self, name: str, min_replicas: int, max_replicas: int) -> dict[str, Any]:
        body = json.dumps(sparse_scale_patch(min_replicas, max_replicas)).encode()
        poller = self.apps.container_apps.begin_update(
            self.resource_group, validate_app_name(name), body, content_type="application/json"
        )
        return app_summary(poller.result())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
