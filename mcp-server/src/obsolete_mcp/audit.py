"""Audit trail. Every tool call becomes an Application Insights custom event (AppEvents in Log Analytics).

Custom events use the documented `microsoft.custom_event.name` attribute on a Python log record.
Telemetry export is only switched on when APPLICATIONINSIGHTS_CONNECTION_STRING is set; locally it is plain JSON logs.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from typing import Any

AUDIT_LOGGER = "obsolete_mcp.audit"
log = logging.getLogger(AUDIT_LOGGER)
current_client: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_client", default="unknown")


def configure() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.setLevel(logging.INFO)
    # The Azure SDK logs every HTTP request and response header at INFO (including each telemetry upload).
    # That floods the console log table you pay to ingest, so keep only its warnings.
    logging.getLogger("azure").setLevel(logging.WARNING)
    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.identity import DefaultAzureCredential
        from microsoft.opentelemetry import use_microsoft_opentelemetry

        # Entra ID auth for ingestion (the Application Insights resource has local auth disabled).
        use_microsoft_opentelemetry(
            enable_azure_monitor=True,
            azure_monitor_exporter_credential=DefaultAzureCredential(),
            logger_name=AUDIT_LOGGER,
        )


_RESERVED = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {"message", "asctime"}


def event(name: str, **fields: Any) -> dict[str, Any]:
    record = {"client": current_client.get(), **fields}
    flat = {(f"mcp_{k}" if k in _RESERVED else k): (v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str))
            for k, v in record.items()}
    log.info("%s %s", name, json.dumps(record, default=str), extra={"microsoft.custom_event.name": name, **flat})
    return record
