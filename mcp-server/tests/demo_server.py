"""Run the real server over HTTP with the fake backend, for MCP Inspector and manual testing.

  MCP_API_KEYS="local:$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" python tests/demo_server.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from fakes import FakeBackend  # noqa: E402

from obsolete_mcp.server import create_app  # noqa: E402
from obsolete_mcp.settings import Settings  # noqa: E402

port = int(os.environ.get("PORT", "8000"))
settings = Settings("demo", "rg-demo", None, os.environ["MCP_API_KEYS"], os.environ.get("ALLOW_WRITES") == "true", 5,
                    [f"localhost:{port}", f"127.0.0.1:{port}"], port)
uvicorn.run(create_app(settings, FakeBackend()), host="127.0.0.1", port=port)
