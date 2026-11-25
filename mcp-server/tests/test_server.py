import json

import pytest
from fakes import TAGS, FakeBackend
from mcp import Client

from obsolete_mcp import server as srv
from obsolete_mcp.settings import Settings

pytestmark = pytest.mark.anyio


def settings(**over):
    base = dict(subscription_id="s", resource_group="rg-demo", workspace_id="w", api_keys_raw="", allow_writes=True,
                max_step=5, allowed_hosts=[], port=8000)
    base.update(over)
    return Settings(**base)


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def call(server, name, args=None):
    async with Client(server) as client:
        res = await client.call_tool(name, args or {})
        assert not res.is_error, res.content
        return res.structured_content


async def test_tools_listed_with_annotations():
    s = srv.build_server(FakeBackend(), settings())
    async with Client(s) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"list_apps", "get_status", "get_contract", "get_baseline", "get_scaling_timeline",
                          "get_recent_changes", "get_alerts", "get_agent_activity", "set_scale_range"}
    assert all(tools[n].annotations.read_only_hint for n in tools if n != "set_scale_range")
    assert tools["set_scale_range"].annotations.read_only_hint is False


async def test_status_and_contract():
    s = srv.build_server(FakeBackend(), settings())
    st = await call(s, "get_status", {"app": "ca-demo-web"})
    assert st["contract"]["max_replicas"] == 10 and st["replicasNow"] is not None and "tags" not in st


async def test_baseline_and_timeline():
    s = srv.build_server(FakeBackend(), settings())
    b = await call(s, "get_baseline", {"app": "ca-demo-web", "days": 14})
    assert b["days"] == 14 and len(b["busiestSlots"]) > 0
    tl = await call(s, "get_scaling_timeline", {"app": "ca-demo-web", "hours": 3})
    kinds = {e["kind"] for e in tl["events"]}
    assert {"scaling", "change", "alert", "agent"} <= kinds
    assert any("load rose" in e["why"] for e in tl["events"] if e["kind"] == "scaling")


async def test_scale_dry_run_by_default():
    fb = FakeBackend()
    s = srv.build_server(fb, settings())
    r = await call(s, "set_scale_range", {"app": "ca-demo-web", "min_replicas": 3, "max_replicas": 10,
                                          "reason": "pre-warm for the Monday 09:00 peak"})
    assert r["allowed"] and not r["applied"] and fb.writes == [] and "applyCommand" in r


async def test_scale_applies_inside_contract():
    fb = FakeBackend()
    s = srv.build_server(fb, settings())
    r = await call(s, "set_scale_range", {"app": "ca-demo-web", "min_replicas": 3, "max_replicas": 10,
                                          "reason": "pre-warm for the Monday 09:00 peak", "dry_run": False})
    assert r["applied"] and fb.writes == [("ca-demo-web", 3, 10)] and r["now"] == [3, 10]


async def test_scale_outside_contract_rejected():
    fb = FakeBackend()
    s = srv.build_server(fb, settings())
    r = await call(s, "set_scale_range", {"app": "ca-demo-web", "min_replicas": 1, "max_replicas": 12,
                                          "reason": "black friday traffic is coming", "dry_run": False})
    assert not r["allowed"] and not r["applied"] and fb.writes == []


async def test_review_mode_never_writes():
    fb = FakeBackend(tags={**TAGS, "aiops-change-mode": "review"})
    s = srv.build_server(fb, settings())
    r = await call(s, "set_scale_range", {"app": "ca-demo-web", "min_replicas": 3, "max_replicas": 10,
                                          "reason": "pre-warm for the Monday 09:00 peak", "dry_run": False})
    assert r["allowed"] and not r["applied"] and r["mode"] == "review" and fb.writes == []


async def test_writes_disabled_never_writes():
    fb = FakeBackend()
    s = srv.build_server(fb, settings(allow_writes=False))
    r = await call(s, "set_scale_range", {"app": "ca-demo-web", "min_replicas": 3, "max_replicas": 10,
                                          "reason": "pre-warm for the Monday 09:00 peak", "dry_run": False})
    assert not r["applied"] and fb.writes == []


async def test_audit_events_emitted(caplog):
    caplog.set_level("INFO", logger="obsolete_mcp.audit")
    s = srv.build_server(FakeBackend(), settings())
    await call(s, "set_scale_range", {"app": "ca-demo-web", "min_replicas": 3, "max_replicas": 10,
                                      "reason": "pre-warm for the Monday 09:00 peak"})
    names = [getattr(r, "microsoft.custom_event.name", None) for r in caplog.records]
    assert "McpToolCall" in names and "McpScaleDecision" in names
    rec = [r for r in caplog.records if getattr(r, "microsoft.custom_event.name", None) == "McpScaleDecision"][0]
    assert rec.decision == "proposed" and json.loads(rec.envelope) == [1, 10]


async def test_invalid_app_name_is_an_error():
    s = srv.build_server(FakeBackend(), settings())
    async with Client(s) as client:
        res = await client.call_tool("get_status", {"app": "x' | drop"})
    assert res.is_error
