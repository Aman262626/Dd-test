"""WiFi Scanner - FastAPI Backend.

Provides REST API endpoints for WiFi network scanning,
history tracking, and data export.
"""

import csv
import io
import json
from collections import defaultdict
from datetime import datetime

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from scanner import WiFiNetwork, get_scan_summary, scan_networks
from stress_test import (
    get_default_gateway,
    run_bandwidth_estimate_test,
    run_concurrent_connection_test,
    run_full_stress_test,
    run_latency_under_load_test,
    run_ping_test,
    run_rapid_ping_test,
)

app = FastAPI(
    title="WiFi Scanner Pro",
    description="Advanced WiFi network scanner with visualization and analytics",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory scan history
scan_history: list[dict] = []
network_history: dict[str, list[dict]] = defaultdict(list)
MAX_HISTORY = 100
MAX_SIGNAL_HISTORY = 50


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main scanner UI."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/scan")
async def api_scan():
    """Perform a WiFi scan and return results."""
    networks = scan_networks()
    summary = get_scan_summary(networks)
    timestamp = datetime.utcnow().isoformat()

    scan_entry = {
        "timestamp": timestamp,
        "network_count": len(networks),
        "networks": [n.to_dict() for n in networks],
    }

    scan_history.append(scan_entry)
    if len(scan_history) > MAX_HISTORY:
        scan_history.pop(0)

    for net in networks:
        net.last_seen = timestamp
        entry = {
            "timestamp": timestamp,
            "signal_strength": net.signal_strength,
            "signal_quality": net.signal_quality,
        }
        network_history[net.bssid].append(entry)
        if len(network_history[net.bssid]) > MAX_SIGNAL_HISTORY:
            network_history[net.bssid].pop(0)

    return {
        "status": "success",
        "timestamp": timestamp,
        "networks": [n.to_dict() for n in networks],
        "summary": summary,
    }


@app.get("/api/history")
async def api_history(limit: int = Query(default=20, ge=1, le=100)):
    """Get scan history."""
    entries = scan_history[-limit:]
    return {
        "status": "success",
        "count": len(entries),
        "history": entries,
    }


@app.get("/api/network/{bssid}/history")
async def api_network_history(bssid: str):
    """Get signal strength history for a specific network."""
    bssid_clean = bssid.upper().replace("-", ":")
    history = network_history.get(bssid_clean, [])
    return {
        "status": "success",
        "bssid": bssid_clean,
        "history": history,
    }


@app.get("/api/export/csv")
async def export_csv():
    """Export last scan results as CSV."""
    if not scan_history:
        return {"status": "error", "message": "No scan data available. Run a scan first."}

    last_scan = scan_history[-1]
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "SSID", "BSSID", "Signal (dBm)", "Quality (%)",
        "Channel", "Frequency", "Encryption", "Mode",
        "Band", "Speed", "Vendor", "Last Seen",
    ])

    for net in last_scan["networks"]:
        writer.writerow([
            net["ssid"], net["bssid"], net["signal_strength"],
            net["signal_quality"], net["channel"], net["frequency"],
            net["encryption"], net["mode"], net["band"],
            net["speed"], net["vendor"], net["last_seen"],
        ])

    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=wifi_scan_{timestamp}.csv"
        },
    )


@app.get("/api/export/json")
async def export_json():
    """Export last scan results as JSON."""
    if not scan_history:
        return {"status": "error", "message": "No scan data available. Run a scan first."}

    last_scan = scan_history[-1]
    output = json.dumps(last_scan, indent=2)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    return StreamingResponse(
        iter([output]),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=wifi_scan_{timestamp}.json"
        },
    )


@app.get("/api/stats")
async def api_stats():
    """Get aggregated statistics across all scans."""
    if not scan_history:
        return {"status": "success", "scans_performed": 0, "data": None}

    total_scans = len(scan_history)
    all_bssids = set()
    for entry in scan_history:
        for net in entry["networks"]:
            all_bssids.add(net["bssid"])

    scan_counts = [entry["network_count"] for entry in scan_history]

    return {
        "status": "success",
        "scans_performed": total_scans,
        "unique_networks_seen": len(all_bssids),
        "avg_networks_per_scan": sum(scan_counts) / len(scan_counts),
        "max_networks_in_scan": max(scan_counts),
        "min_networks_in_scan": min(scan_counts),
        "first_scan": scan_history[0]["timestamp"],
        "last_scan": scan_history[-1]["timestamp"],
    }


@app.get("/api/channel-analysis")
async def channel_analysis():
    """Analyze channel congestion from latest scan."""
    if not scan_history:
        return {"status": "error", "message": "No scan data available."}

    last_scan = scan_history[-1]
    channels_2g: dict[int, list] = defaultdict(list)
    channels_5g: dict[int, list] = defaultdict(list)

    for net in last_scan["networks"]:
        ch = net["channel"]
        entry = {
            "ssid": net["ssid"],
            "signal_strength": net["signal_strength"],
            "encryption": net["encryption"],
        }
        if "2.4" in net.get("band", ""):
            channels_2g[ch].append(entry)
        else:
            channels_5g[ch].append(entry)

    best_2g = None
    best_5g = None

    # Find least congested channels
    all_2g_channels = list(range(1, 14))
    all_5g_channels = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108,
                       112, 116, 120, 124, 128, 132, 136, 140, 149, 153,
                       157, 161, 165]

    min_count_2g = float("inf")
    for ch in all_2g_channels:
        count = len(channels_2g.get(ch, []))
        if count < min_count_2g:
            min_count_2g = count
            best_2g = ch

    min_count_5g = float("inf")
    for ch in all_5g_channels:
        count = len(channels_5g.get(ch, []))
        if count < min_count_5g:
            min_count_5g = count
            best_5g = ch

    return {
        "status": "success",
        "channels_2ghz": {str(k): v for k, v in sorted(channels_2g.items())},
        "channels_5ghz": {str(k): v for k, v in sorted(channels_5g.items())},
        "recommended_2ghz": best_2g,
        "recommended_5ghz": best_5g,
    }


# --- Stress Test Endpoints ---


@app.get("/api/stress/gateway")
async def stress_gateway():
    """Get the detected default gateway."""
    gateway = get_default_gateway()
    return {"status": "success", "gateway": gateway}


@app.get("/api/stress/ping")
async def stress_ping(host: str | None = None, count: int = Query(default=20, ge=5, le=100)):
    """Run a basic ping test against the gateway or specified host."""
    if not host:
        host = get_default_gateway() or "192.168.1.1"
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_ping_test, host, count)
    from dataclasses import asdict
    return {"status": "success", "result": asdict(result)}


@app.get("/api/stress/rapid-ping")
async def stress_rapid_ping(host: str | None = None, count: int = Query(default=50, ge=10, le=200)):
    """Run a rapid ping stress test."""
    if not host:
        host = get_default_gateway() or "192.168.1.1"
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_rapid_ping_test, host, count)
    from dataclasses import asdict
    return {"status": "success", "result": asdict(result)}


@app.get("/api/stress/connections")
async def stress_connections(host: str | None = None, max_connections: int = Query(default=60, ge=10, le=200)):
    """Test concurrent connection handling."""
    if not host:
        host = get_default_gateway() or "192.168.1.1"
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_concurrent_connection_test, host, max_connections)
    return {"status": "success", "result": result}


@app.get("/api/stress/latency-load")
async def stress_latency_load(host: str | None = None, duration: int = Query(default=8, ge=3, le=30)):
    """Measure latency under network load."""
    if not host:
        host = get_default_gateway() or "192.168.1.1"
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_latency_under_load_test, host, duration)
    return {"status": "success", "result": result}


@app.get("/api/stress/bandwidth")
async def stress_bandwidth(host: str | None = None):
    """Estimate bandwidth capacity."""
    if not host:
        host = get_default_gateway() or "192.168.1.1"
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_bandwidth_estimate_test, host)
    return {"status": "success", "result": result}


@app.get("/api/stress/full")
async def stress_full(host: str | None = None):
    """Run the complete stress test suite."""
    result = await run_full_stress_test(host)
    return {"status": "success", "result": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
