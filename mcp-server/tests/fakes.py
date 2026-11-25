from __future__ import annotations

from datetime import datetime, timedelta, timezone

APP_ID = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo/providers/Microsoft.App/containerApps/ca-demo-web"

TAGS = {
    "aiops-managed": "true", "aiops-owner": "platform-team@contoso.com", "aiops-min-replicas": "1",
    "aiops-max-replicas": "10", "aiops-change-mode": "autonomous", "aiops-tier": "nonprod",
    "aiops-slo-p95-ms": "300", "aiops-budget-eur": "50",
}


class FakeBackend:
    resource_group = "rg-demo"

    def __init__(self, tags=None, now=None):
        self.now = now or datetime.now(timezone.utc).replace(second=0, microsecond=0)
        self.app = {
            "id": APP_ID, "name": "ca-demo-web", "location": "swedencentral", "tags": dict(tags or TAGS),
            "provisioningState": "Succeeded", "runningStatus": "Running", "latestRevision": "ca-demo-web--r1",
            "latestReadyRevision": "ca-demo-web--r1", "fqdn": "ca-demo-web.example.swedencentral.azurecontainerapps.io",
            "minReplicas": 1, "maxReplicas": 10,
            "scaleRules": [{"name": "http-concurrency", "kind": "http", "metadata": {"concurrentRequests": "50"}}],
        }
        self.writes: list[tuple[str, int, int]] = []

    def list_apps(self):
        return [dict(self.app)]

    def get_app(self, name):
        if name != self.app["name"]:
            raise LookupError(name)
        return dict(self.app, tags=dict(self.app["tags"]))

    def metric_series(self, resource_id, metrics, aggregation, start, end, interval):
        out = {}
        step = timedelta(hours=1) if interval == "PT1H" else timedelta(minutes=1)
        for m in metrics:
            pts, t = [], start.replace(second=0, microsecond=0)
            while t <= end:
                if m == "Requests":
                    busy = 9 <= t.hour < 17 and t.weekday() < 5
                    v = (6000.0 if busy else 600.0) if step.seconds == 3600 else (400.0 if t >= end - timedelta(minutes=30) else 100.0)
                else:
                    busy = 9 <= t.hour < 17 and t.weekday() < 5
                    v = (4.0 if busy else 1.0) if step.seconds == 3600 else (3.0 if t >= end - timedelta(minutes=29) else 1.0)
                pts.append((t, v))
                t += step
            out[m] = pts
        return out

    def resource_changes(self, hours):
        return [{"changeTime": (self.now - timedelta(hours=2)).isoformat(), "targetResourceId": APP_ID,
                 "changeType": "Update", "changedBy": "gisli@contoso.com", "clientType": "Azure Portal",
                 "operation": "Microsoft.App/containerApps/write", "changes": {}}]

    def alerts(self, hours):
        return [{"startTime": (self.now - timedelta(minutes=40)).isoformat(), "name": "ma-demo-requests-anomaly",
                 "severity": "Sev3", "monitorCondition": "Fired", "alertRule": "x", "targetResource": APP_ID}]

    def agent_events(self, hours):
        return [{"TimeGenerated": (self.now - timedelta(minutes=10)).isoformat(), "Name": "AgentToolExecution",
                 "AppRoleName": "sre-agent", "Properties": {"ToolName": "SearchResource", "EventType": "ToolStart"}}]

    def set_scale_range(self, name, lo, hi):
        self.writes.append((name, lo, hi))
        self.app.update(minReplicas=lo, maxReplicas=hi, latestRevision="ca-demo-web--r2")
        return dict(self.app)
