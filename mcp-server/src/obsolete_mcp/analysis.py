"""Baseline and timeline maths. Pure functions over data the backend returns, so they are unit-tested offline."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pct(values: list[float], p: float) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return vals[lo] if lo == hi else vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def hour_of_week_baseline(
    requests: list[tuple[datetime, float | None]],
    replicas: list[tuple[datetime, float | None]],
    now: datetime,
    contract_min: int,
    contract_max: int,
) -> dict[str, Any]:
    """Median and p90 of hourly request totals per hour-of-week, plus typical replicas, from hourly metric points.

    Returns what the current hour normally looks like and a contract-clipped suggestion for minReplicas
    for the next hour (the median of the max replica count seen in that hour-of-week).
    """
    req_by_slot: dict[tuple[int, int], list[float]] = defaultdict(list)
    rep_by_slot: dict[tuple[int, int], list[float]] = defaultdict(list)
    for ts, v in requests:
        if v is not None:
            req_by_slot[(ts.weekday(), ts.hour)].append(float(v))
    for ts, v in replicas:
        if v is not None:
            rep_by_slot[(ts.weekday(), ts.hour)].append(float(v))

    def slot_info(slot: tuple[int, int]) -> dict[str, Any]:
        r = req_by_slot.get(slot, [])
        p = rep_by_slot.get(slot, [])
        return {
            "slot": f"{WEEKDAYS[slot[0]]} {slot[1]:02d}:00 UTC",
            "samples": len(r),
            "requestsMedian": round(statistics.median(r), 1) if r else None,
            "requestsP90": round(_pct(r, 0.9), 1) if r else None,
            "replicasMedian": statistics.median(p) if p else None,
        }

    current_slot = (now.weekday(), now.hour)
    nxt = now + timedelta(hours=1)
    next_slot = (nxt.weekday(), nxt.hour)
    last_full_hour = [(ts, v) for ts, v in requests if v is not None and ts <= now - timedelta(hours=1)]
    last_value = last_full_hour[-1][1] if last_full_hour else None
    cur = slot_info(current_slot)
    deviation = None
    if last_value is not None and cur["requestsMedian"]:
        deviation = round(last_value / cur["requestsMedian"], 2)

    nxt_info = slot_info(next_slot)
    suggested_min = None
    if nxt_info["replicasMedian"] is not None:
        suggested_min = int(min(max(math.ceil(nxt_info["replicasMedian"]), contract_min), contract_max))

    weekly = [slot_info((d, h)) for d in range(7) for h in range(24)]
    busiest = sorted((w for w in weekly if w["requestsMedian"] is not None), key=lambda w: -w["requestsMedian"])[:5]
    return {
        "currentSlot": cur,
        "lastFullHourRequests": last_value,
        "ratioToMedian": deviation,
        "nextSlot": nxt_info,
        "suggestedMinReplicasNextHour": suggested_min,
        "busiestSlots": busiest,
        "note": "Baseline = median/p90 of hourly Requests totals per hour-of-week from Azure Monitor platform metrics.",
    }


def replica_changes(
    replicas: list[tuple[datetime, float | None]], requests: list[tuple[datetime, float | None]]
) -> list[dict[str, Any]]:
    """Every minute where the max replica count differs from the previous known minute, with the load around it."""
    req = {ts: (v or 0.0) for ts, v in requests}
    out = []
    prev = None
    for ts, v in replicas:
        if v is None:
            continue
        if prev is not None and v != prev:
            window = [req.get(ts - timedelta(minutes=i), 0.0) for i in range(2, 7)]
            before = sum(window) / 5
            # Metric minutes and replica minutes don't line up exactly: the load that triggered a scale-out
            # is often in the minute before the replica count moved, so look at both.
            recent = max(req.get(ts, 0.0), req.get(ts - timedelta(minutes=1), 0.0))
            lookback = [(ts - timedelta(minutes=i), req.get(ts - timedelta(minutes=i), 0.0)) for i in range(1, 16)]
            peak_ts, peak = max(lookback, key=lambda p: p[1])
            out.append(
                {
                    "time": ts,
                    "from": int(prev),
                    "to": int(v),
                    "direction": "scale-out" if v > prev else "scale-in",
                    "requestsThisMinute": req.get(ts),
                    "requestsRecent": recent,
                    "requestsAvgPrev5Min": round(before, 1),
                    "requestsPeakPrev15Min": peak,
                    "requestsPeakTime": peak_ts,
                }
            )
        prev = v
    return out


SCALE_KEYS = ("scale", "template")


def _touches_scale(change: dict[str, Any]) -> bool:
    """True when a resource change could have moved the replica count. Without a diff we can't tell, so assume yes."""
    diff = change.get("changes")
    if diff is None:
        return True
    return any(k in str(path).lower() for path in diff for k in SCALE_KEYS)


def explain(change: dict[str, Any], config_changes: list[dict[str, Any]], alerts: list[dict[str, Any]], app_id: str) -> str:
    """A plain-language reason for one replica change.

    Order: a configuration change on the app that touched its scale settings, then load, then an alert on the app.
    An alert such as "replica ceiling reached" is usually a consequence of scaling, not its cause, so load wins.
    """
    t = change["time"]
    for c in config_changes:
        ct = c.get("time")
        if (ct and c.get("targetResourceId", "").lower() == app_id.lower() and t - timedelta(minutes=10) <= ct <= t
                and _touches_scale(c)):
            who = c.get("changedBy") or "unknown"
            return f"configuration change on the app at {ct:%H:%M} by {who} ({c.get('clientType') or 'unknown client'})"
    recent = change.get("requestsRecent", change.get("requestsThisMinute")) or 0
    before = change.get("requestsAvgPrev5Min") or 0
    if change["direction"] == "scale-out" and recent > 0 and (before == 0 or recent > before * 1.2):
        return f"load rose: {recent:.0f} requests/min against {before:.0f} avg in the 5 min before (HTTP/CPU rule)"
    peak = change.get("requestsPeakPrev15Min") or 0
    now_req = change.get("requestsThisMinute") or 0
    if change["direction"] == "scale-in" and peak > 0 and now_req < peak * 0.8:
        pt = change.get("requestsPeakTime")
        at = f" at {pt:%H:%M}" if pt else ""
        return (f"load fell: {now_req:.0f} requests/min now against a peak of {peak:.0f}{at}; "
                "scale-in after the scale-down stabilization window (300 s)")
    for a in alerts:
        at = a.get("time")
        target = (a.get("targetResource") or app_id).lower()
        if at and target == app_id.lower() and t - timedelta(minutes=10) <= at <= t:
            return f"alert '{a.get('name')}' fired at {at:%H:%M}"
    if change["direction"] == "scale-out":
        return "scale rule fired (HTTP concurrency or CPU); request volume alone does not explain it"
    return "scale-in after the scale-down stabilization window (300 s)"


def build_timeline(
    app: dict[str, Any],
    replicas: list[tuple[datetime, float | None]],
    requests: list[tuple[datetime, float | None]],
    changes: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    agent_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One ordered list of what happened: scaling, configuration changes, alerts, agent actions."""
    cfg = [
        {
            "time": _dt(c.get("changeTime")),
            "targetResourceId": c.get("targetResourceId", ""),
            "changedBy": c.get("changedBy"),
            "clientType": c.get("clientType"),
            "changeType": c.get("changeType"),
            "changes": c.get("changes"),
        }
        for c in changes
    ]
    al = [{"time": _dt(a.get("startTime")), "name": a.get("name"), "severity": a.get("severity"),
           "condition": a.get("monitorCondition"), "targetResource": a.get("targetResource")} for a in alerts]
    events: list[dict[str, Any]] = []
    for ch in replica_changes(replicas, requests):
        events.append({"time": ch["time"], "kind": "scaling",
                       "summary": f"{ch['direction']} {ch['from']} -> {ch['to']} replicas",
                       "why": explain(ch, cfg, al, app["id"])})
    for c in cfg:
        if c["time"]:
            name = c["targetResourceId"].rsplit("/", 1)[-1]
            events.append({"time": c["time"], "kind": "change",
                           "summary": f"{c['changeType'] or 'Update'} on {name} by {c['changedBy'] or 'unknown'}",
                           "why": f"client: {c['clientType'] or 'unknown'}"})
    for a in al:
        if a["time"]:
            events.append({"time": a["time"], "kind": "alert",
                           "summary": f"{a['severity'] or ''} {a['name']} ({a['condition'] or 'Fired'})".strip(), "why": ""})
    for e in agent_events:
        t = _dt(e.get("TimeGenerated"))
        if not t:
            continue
        p = e.get("Properties") or {}
        tool = p.get("ToolName") or p.get("tool") or ""
        events.append({"time": t, "kind": "agent",
                       "summary": f"{e.get('Name')} {tool} {p.get('EventType', '') or p.get('decision', '')}".strip(),
                       "why": str(p.get("reason", ""))[:200]})
    events.sort(key=lambda x: x["time"])
    for e in events:
        e["time"] = e["time"].isoformat()
    return events


def _dt(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
