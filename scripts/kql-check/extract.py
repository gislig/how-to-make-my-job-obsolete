"""Write every KQL query that is embedded in code to a folder, so check.js can parse and check it.

Sources: the MCP server's query builders (mcp-server/src/obsolete_mcp/backend.py) and the log alert
queries in Bicep (`query: '...'` lines). Usage: python extract.py <out-dir>
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(root / "mcp-server" / "src"))
from obsolete_mcp import backend  # noqa: E402

(out / "server-resource-changes.kql").write_text(backend.resource_changes_query("rg-demo", 24))
(out / "server-alerts.kql").write_text(backend.alerts_query("rg-demo", 24))
(out / "server-agent-events.kql").write_text(backend.agent_events_query(24))

for bicep in sorted((root / "infra").rglob("*.bicep")):
    for i, m in enumerate(re.finditer(r"^\s*query: '(.*)'\s*$", bicep.read_text(), re.M)):
        q = m.group(1).replace("${resourceGroup().name}", "rg-demo").replace("\\'", "'")
        (out / f"bicep-{bicep.stem}-{i}.kql").write_text(q)

print(f"extracted {len(list(out.glob('*.kql')))} embedded queries to {out}")
