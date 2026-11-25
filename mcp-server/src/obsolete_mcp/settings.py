from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    subscription_id: str
    resource_group: str
    workspace_id: str | None
    api_keys_raw: str
    allow_writes: bool
    max_step: int
    allowed_hosts: list[str]
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
        return cls(
            subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID", ""),
            resource_group=os.environ.get("AIOPS_RESOURCE_GROUP", ""),
            workspace_id=os.environ.get("LOG_ANALYTICS_WORKSPACE_ID") or None,
            api_keys_raw=os.environ.get("MCP_API_KEYS", ""),
            allow_writes=os.environ.get("ALLOW_WRITES", "false").lower() == "true",
            max_step=int(os.environ.get("MAX_STEP", "5")),
            allowed_hosts=hosts,
            port=int(os.environ.get("PORT", "8000")),
        )
