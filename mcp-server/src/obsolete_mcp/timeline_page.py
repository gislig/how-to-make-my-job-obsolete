"""The timeline page: one static HTML file showing what happened to an app and why.

  az login
  python -m obsolete_mcp.timeline_page --subscription <id> --resource-group <rg> --app <name> \
      [--workspace-id <log-analytics-workspace-guid>] [--hours 24] --out timeline.html

Same data and the same `build_timeline` logic as the MCP tool get_scaling_timeline, so the page and the chat answer agree.
"""

from __future__ import annotations

import argparse
import html
from datetime import timedelta
from typing import Any

from .analysis import build_timeline
from .backend import AzureBackend, Backend, utcnow

COLORS = {"scaling": "#2563eb", "change": "#d97706", "alert": "#dc2626", "agent": "#7c3aed"}


def collect(backend: Backend, app_name: str, hours: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    app = backend.get_app(app_name)
    end = utcnow()
    start = end - timedelta(hours=hours)
    rep = backend.metric_series(app["id"], ["Replicas"], "Maximum", start, end, "PT1M")
    req = backend.metric_series(app["id"], ["Requests"], "Total", start, end, "PT1M")
    events = build_timeline(app, rep.get("Replicas", []), req.get("Requests", []), backend.resource_changes(hours),
                            backend.alerts(hours), backend.agent_events(hours))
    return app, events


def render_html(app: dict[str, Any], events: list[dict[str, Any]], hours: int) -> str:
    e = html.escape
    rows = []
    for ev in reversed(events):
        color = COLORS.get(ev["kind"], "#475569")
        why = f'<div class="why">{e(ev["why"])}</div>' if ev.get("why") else ""
        rows.append(
            f'<li><span class="dot" style="background:{color}"></span>'
            f'<time>{e(ev["time"].replace("T", " ")[:19])} UTC</time> '
            f'<span class="kind" style="color:{color}">{e(ev["kind"])}</span> '
            f'<span class="sum">{e(ev["summary"])}</span>{why}</li>'
        )
    legend = " ".join(f'<span style="color:{c}">&#9679; {k}</span>' for k, c in COLORS.items())
    body = "\n".join(rows) or "<li>No events in this window.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Timeline: {e(app['name'])}</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#0f172a}}
ul{{list-style:none;padding-left:1.2rem;border-left:2px solid #cbd5e1}}
li{{position:relative;margin:0 0 1rem 0;padding-left:.8rem}}
.dot{{position:absolute;left:-1.75rem;top:.4rem;width:.8rem;height:.8rem;border-radius:50%}}
time{{color:#475569;font-variant-numeric:tabular-nums}} .kind{{font-weight:600;text-transform:uppercase;font-size:.8rem}}
.why{{color:#334155;font-size:.9rem}}
</style></head><body>
<h1>{e(app['name'])}: the last {hours} hours</h1>
<p>Scale range now: {app.get('minReplicas')} to {app.get('maxReplicas')} replicas. Revision {e(str(app.get('latestRevision')))}.</p>
<p>{legend}</p>
<ul>
{body}
</ul>
<p><small>Generated {e(utcnow().isoformat()[:19])} UTC from Azure Monitor metrics, Azure Resource Graph and Log Analytics.</small></p>
</body></html>"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--subscription", required=True)
    p.add_argument("--resource-group", required=True)
    p.add_argument("--app", required=True)
    p.add_argument("--workspace-id", default=None)
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--out", default="timeline.html")
    a = p.parse_args()
    backend = AzureBackend(a.subscription, a.resource_group, a.workspace_id)
    app, events = collect(backend, a.app, max(1, min(a.hours, 24 * 14)))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render_html(app, events, a.hours))
    print(f"wrote {a.out} with {len(events)} events")


if __name__ == "__main__":
    main()
