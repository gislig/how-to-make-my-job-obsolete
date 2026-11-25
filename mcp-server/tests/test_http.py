"""End to end over real HTTP: uvicorn + Streamable HTTP + API key middleware + the MCP client."""

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fakes import FakeBackend
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from obsolete_mcp.server import create_app
from obsolete_mcp.settings import Settings

pytestmark = pytest.mark.anyio
KEY = "k" * 48


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def base_url():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    settings = Settings("s", "rg-demo", None, f"grokbot:{KEY}", False, 5, [f"127.0.0.1:{port}"], port)
    server = uvicorn.Server(uvicorn.Config(create_app(settings, FakeBackend()), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=0.2)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


def test_healthz_is_open(base_url):
    r = httpx.get(f"{base_url}/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_mcp_requires_key(base_url):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    hdr = {"accept": "application/json, text/event-stream"}
    assert httpx.post(f"{base_url}/mcp", json=body, headers=hdr).status_code == 401
    assert httpx.post(f"{base_url}/mcp", json=body, headers={**hdr, "x-api-key": "wrong"}).status_code == 401


def test_wrong_host_header_rejected(base_url):
    r = httpx.post(f"{base_url}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                   headers={"x-api-key": KEY, "host": "evil.example", "accept": "application/json, text/event-stream"})
    assert r.status_code in (400, 403, 421)


@pytest.mark.parametrize("headers", [{"Authorization": f"Bearer {KEY}"}, {"X-API-Key": KEY}])
async def test_client_over_http(base_url, headers):
    async with httpx.AsyncClient(headers=headers) as http:
        async with Client(streamable_http_client(f"{base_url}/mcp", http_client=http)) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert "get_scaling_timeline" in names
            res = await client.call_tool("set_scale_range", {"app": "ca-demo-web", "min_replicas": 3, "max_replicas": 10,
                                                             "reason": "pre-warm for the Monday 09:00 peak", "dry_run": False})
            sc = res.structured_content
            assert sc["allowed"] and not sc["applied"]  # ALLOW_WRITES is false on this server


async def test_audit_records_which_client_called(base_url, caplog):
    caplog.set_level("INFO", logger="obsolete_mcp.audit")
    async with httpx.AsyncClient(headers={"X-API-Key": KEY}) as http:
        async with Client(streamable_http_client(f"{base_url}/mcp", http_client=http)) as client:
            await client.call_tool("get_contract", {"app": "ca-demo-web"})
    recs = [r for r in caplog.records if getattr(r, "microsoft.custom_event.name", None) == "McpToolCall"]
    assert recs and recs[-1].client == "grokbot"
