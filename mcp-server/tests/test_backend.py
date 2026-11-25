import pytest
from azure.mgmt.appcontainers import models

from obsolete_mcp.backend import (agent_events_query, alerts_query, app_summary, resource_changes_query,
                                  sparse_scale_patch, validate_app_name)


def test_sparse_patch_matches_az_cli_body():
    # az containerapp update --min-replicas 2 --max-replicas 8 sends only template.scale min/max (rules are popped)
    assert sparse_scale_patch(2, 8) == {"properties": {"template": {"scale": {"minReplicas": 2, "maxReplicas": 8}}}}


@pytest.mark.parametrize("bad", ["", "A", "x' or 1==1", "a" * 40, "-abc", "abc-", "ab c"])
def test_app_name_validation(bad):
    with pytest.raises(ValueError):
        validate_app_name(bad)


def test_queries_are_scoped():
    assert "/resourceGroups/rg-demo/" in resource_changes_query("rg-demo", 24)
    assert "ago(24h)" in alerts_query("rg-demo", 24)
    assert "AppEvents" in agent_events_query(6) and "ago(6h)" in agent_events_query(6)


def test_app_summary_on_real_sdk_model():
    raw = {"id": "/x", "name": "n", "location": "swedencentral", "tags": {"aiops-managed": "true"},
           "properties": {"provisioningState": "Succeeded", "runningStatus": "Running", "latestRevisionName": "n--r1",
                          "configuration": {"ingress": {"fqdn": "n.example"}},
                          "template": {"scale": {"minReplicas": 1, "maxReplicas": 5, "rules": [
                              {"name": "h", "http": {"metadata": {"concurrentRequests": "50"}}},
                              {"name": "c", "custom": {"type": "cpu", "metadata": {"type": "Utilization", "value": "70"}}}]}}}}
    s = app_summary(models.ContainerApp(raw))
    assert s["minReplicas"] == 1 and s["maxReplicas"] == 5 and s["fqdn"] == "n.example"
    assert s["runningStatus"] == "Running" and s["provisioningState"] == "Succeeded"
    assert s["scaleRules"][1] == {"name": "c", "kind": "custom", "metadata": {"scaler": "cpu", "type": "Utilization", "value": "70"}}
