"""API key authentication as a pure ASGI middleware.

Accepted headers (either one):
  Authorization: Bearer <key>
  X-API-Key: <key>

Keys come from MCP_API_KEYS as "client-name:key,other-client:key2". The client name goes into the audit log,
so you can see whether Grok Bot or the SRE Agent made a call, and you can rotate one client without the other.
"""

from __future__ import annotations

import hmac
import json
from typing import Any, Callable

OPEN_PATHS = {"/healthz"}


def parse_keys(raw: str) -> dict[str, str]:
    """'grokbot:abc,sre:def' -> {'abc': 'grokbot', 'def': 'sre'}. Keys shorter than 32 characters are rejected."""
    keys: dict[str, str] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, key = part.partition(":")
        if not sep or not name or len(key) < 32:
            raise ValueError("MCP_API_KEYS entries must look like name:key with a key of at least 32 characters")
        keys[key] = name
    return keys


def match_key(presented: str | None, keys: dict[str, str]) -> str | None:
    if not presented:
        return None
    found = None
    for key, name in keys.items():  # compare against every key in constant time
        if hmac.compare_digest(presented.encode(), key.encode()):
            found = name
    return found


class ApiKeyMiddleware:
    def __init__(self, app: Callable, keys: dict[str, str]):
        if not keys:
            raise ValueError("no API keys configured; refusing to start an unauthenticated MCP server")
        self.app = app
        self.keys = keys

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http" or scope.get("path") in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        presented = headers.get("x-api-key")
        auth = headers.get("authorization", "")
        if not presented and auth.lower().startswith("bearer "):
            presented = auth[7:].strip()
        client = match_key(presented, self.keys)
        if client is None:
            body = json.dumps({"error": "unauthorized"}).encode()
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": body})
            return
        scope.setdefault("state", {})["mcp_client"] = client
        await self.app(scope, receive, send)
