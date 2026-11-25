from datetime import datetime, timedelta, timezone

from obsolete_mcp.analysis import build_timeline, explain, hour_of_week_baseline, replica_changes

T0 = datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)  # Monday


def hourly(days, busy, quiet):
    pts = []
    t = T0 - timedelta(days=days)
    while t < T0:
        pts.append((t, busy if (9 <= t.hour < 17 and t.weekday() < 5) else quiet))
        t += timedelta(hours=1)
    return pts


def test_baseline_suggests_prewarm_before_peak():
    b = hour_of_week_baseline(hourly(28, 6000.0, 600.0), hourly(28, 4.0, 1.0), T0, 1, 10)
    assert b["currentSlot"]["slot"] == "Mon 08:00 UTC"
    assert b["currentSlot"]["requestsMedian"] == 600.0
    assert b["nextSlot"]["requestsMedian"] == 6000.0
    assert b["suggestedMinReplicasNextHour"] == 4  # median replicas at Mon 09:00
    assert b["busiestSlots"][0]["requestsMedian"] == 6000.0


def test_baseline_suggestion_is_clipped_to_contract():
    b = hour_of_week_baseline(hourly(28, 6000.0, 600.0), hourly(28, 40.0, 1.0), T0, 1, 10)
    assert b["suggestedMinReplicasNextHour"] == 10


def minutes(values):
    return [(T0 + timedelta(minutes=i), v) for i, v in enumerate(values)]


def test_replica_changes_and_load_reason():
    reps = minutes([1, 1, 1, 1, 1, 1, 3, 3, 1])
    reqs = minutes([100, 100, 100, 100, 100, 100, 400, 400, 50])
    ch = replica_changes(reps, reqs)
    assert [(c["from"], c["to"], c["direction"]) for c in ch] == [(1, 3, "scale-out"), (3, 1, "scale-in")]
    assert "load rose" in explain(ch[0], [], [], "/id")
    assert "load fell" in explain(ch[1], [], [], "/id")


def test_config_change_wins_over_load():
    reps = minutes([1, 1, 1, 1, 1, 1, 3])
    reqs = minutes([100] * 7)
    ch = replica_changes(reps, reqs)[0]
    cfg = [{"time": T0 + timedelta(minutes=2), "targetResourceId": "/ID", "changedBy": "gisli", "clientType": "Azure CLI"}]
    assert "configuration change" in explain(ch, cfg, [], "/id")


def test_timeline_is_ordered_and_merged():
    app = {"id": "/id"}
    tl = build_timeline(app, minutes([1] * 6 + [3]), minutes([100] * 6 + [400]),
                        [{"changeTime": (T0 - timedelta(hours=1)).isoformat(), "targetResourceId": "/id/x",
                          "changeType": "Update", "changedBy": "gisli", "clientType": "Azure Portal"}],
                        [{"startTime": T0.isoformat(), "name": "a", "severity": "Sev3", "monitorCondition": "Fired"}],
                        [{"TimeGenerated": (T0 + timedelta(minutes=1)).isoformat(), "Name": "AgentToolExecution",
                          "Properties": {"ToolName": "SearchResource", "EventType": "ToolStart"}}])
    assert [e["kind"] for e in tl] == ["change", "alert", "agent", "scaling"]
    assert tl == sorted(tl, key=lambda e: e["time"])


def test_live_regressions_from_first_deployment():
    # Seen on the first live run (25 Nov 2026): a load test from zero, then scale-in long after the load stopped,
    # with an unrelated workspace alert and a no-op `az containerapp update` nearby.
    reps = minutes([1] * 6 + [10] * 11 + [2, 2, 2, 1])
    reqs = minutes([0] * 5 + [90000] + [150000] * 5 + [0] * 10)
    ch = replica_changes(reps, reqs)
    assert [(c["from"], c["to"]) for c in ch] == [(1, 10), (10, 2), (2, 1)]
    assert "load rose" in explain(ch[0], [], [], "/id")
    workspace_alert = [{"time": ch[1]["time"] - timedelta(minutes=5), "name": "mcp-scale-rejected",
                        "targetResource": "/workspaces/log"}]
    why = explain(ch[1], [], workspace_alert, "/id")
    assert "load fell" in why and "mcp-scale-rejected" not in why
    noop = [{"time": ch[2]["time"] - timedelta(minutes=2), "targetResourceId": "/id", "changedBy": "gisli",
             "clientType": "CLI", "changes": {}}]
    assert "configuration change" not in explain(ch[2], noop, [], "/id")
    scale_edit = [dict(noop[0], changes={"properties.template.scale.minReplicas": {"previousValue": 2, "newValue": 1}})]
    assert "configuration change" in explain(ch[2], scale_edit, [], "/id")
