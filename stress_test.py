"""WiFi Stress Test & Network Diagnostics Module.

Provides legitimate network stress testing tools to evaluate
WiFi router resilience, bandwidth capacity, and connection
stability under load. Tests are performed against the local
gateway (your own router) only.
"""

import asyncio
import platform
import re
import socket
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class PingResult:
    host: str
    sent: int
    received: int
    lost: int
    loss_percent: float
    min_ms: float
    avg_ms: float
    max_ms: float
    jitter_ms: float


@dataclass
class StressTestResult:
    test_type: str
    timestamp: str
    duration_seconds: float
    score: int  # 0-100
    grade: str  # A+ to F
    details: dict = field(default_factory=dict)


def get_default_gateway() -> str | None:
    """Detect the default gateway (router) IP address."""
    system = platform.system()
    try:
        if system == "Linux":
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            match = re.search(r"default via (\S+)", result.stdout)
            if match:
                return match.group(1)

            result = subprocess.run(
                ["route", "-n"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("0.0.0.0"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]

        elif system == "Darwin":
            result = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True, text=True, timeout=5,
            )
            match = re.search(r"gateway:\s*(\S+)", result.stdout)
            if match:
                return match.group(1)

        elif system == "Windows":
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True, text=True, timeout=5,
            )
            match = re.search(r"Default Gateway.*?:\s*(\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return "192.168.1.1"


def _parse_ping_output(output: str, count: int) -> dict:
    """Parse ping output across platforms."""
    result = {
        "sent": count,
        "received": 0,
        "min_ms": 0.0,
        "avg_ms": 0.0,
        "max_ms": 0.0,
    }

    recv_match = re.search(r"(\d+)\s+(?:packets\s+)?received", output)
    if recv_match:
        result["received"] = int(recv_match.group(1))

    stats_match = re.search(
        r"(?:rtt|round-trip).*?=\s*([\d.]+)/([\d.]+)/([\d.]+)",
        output,
    )
    if stats_match:
        result["min_ms"] = float(stats_match.group(1))
        result["avg_ms"] = float(stats_match.group(2))
        result["max_ms"] = float(stats_match.group(3))

    return result


def run_ping_test(host: str, count: int = 20) -> PingResult:
    """Run a basic ping test to the target host."""
    system = platform.system()
    count_flag = "-n" if system == "Windows" else "-c"

    try:
        result = subprocess.run(
            ["ping", count_flag, str(count), host],
            capture_output=True, text=True,
            timeout=count * 2 + 10,
        )
        parsed = _parse_ping_output(result.stdout, count)
        lost = parsed["sent"] - parsed["received"]
        loss_pct = (lost / parsed["sent"] * 100) if parsed["sent"] > 0 else 100
        jitter = parsed["max_ms"] - parsed["min_ms"]

        return PingResult(
            host=host,
            sent=parsed["sent"],
            received=parsed["received"],
            lost=lost,
            loss_percent=round(loss_pct, 2),
            min_ms=parsed["min_ms"],
            avg_ms=parsed["avg_ms"],
            max_ms=parsed["max_ms"],
            jitter_ms=round(jitter, 2),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return PingResult(
            host=host, sent=count, received=0, lost=count,
            loss_percent=100.0, min_ms=0, avg_ms=0, max_ms=0, jitter_ms=0,
        )


def run_rapid_ping_test(host: str, count: int = 100) -> PingResult:
    """Run a rapid (flood-style) ping test to stress the connection.

    Uses ping -f on Linux (requires root) or falls back to
    ping -i 0.05 for fast interval pinging.
    """
    system = platform.system()

    if system == "Linux":
        try:
            result = subprocess.run(
                ["ping", "-c", str(count), "-i", "0.05", "-s", "1400", host],
                capture_output=True, text=True,
                timeout=count + 30,
            )
            parsed = _parse_ping_output(result.stdout, count)
            lost = parsed["sent"] - parsed["received"]
            loss_pct = (lost / parsed["sent"] * 100) if parsed["sent"] > 0 else 100
            jitter = parsed["max_ms"] - parsed["min_ms"]

            return PingResult(
                host=host,
                sent=parsed["sent"],
                received=parsed["received"],
                lost=lost,
                loss_percent=round(loss_pct, 2),
                min_ms=parsed["min_ms"],
                avg_ms=parsed["avg_ms"],
                max_ms=parsed["max_ms"],
                jitter_ms=round(jitter, 2),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return run_ping_test(host, count=min(count, 50))


def run_concurrent_connection_test(host: str, max_connections: int = 100) -> dict:
    """Test how many simultaneous TCP connections the router can handle.

    Attempts to open multiple socket connections to common ports
    on the gateway to test connection handling capacity.
    """
    ports_to_test = [80, 443, 53]
    results = {
        "host": host,
        "max_attempted": max_connections,
        "successful_connections": 0,
        "failed_connections": 0,
        "avg_connect_time_ms": 0.0,
        "port_results": {},
    }

    total_time = 0.0
    total_success = 0
    total_fail = 0

    for port in ports_to_test:
        sockets = []
        port_success = 0
        port_fail = 0
        connect_times = []

        conns_per_port = max_connections // len(ports_to_test)

        for _ in range(conns_per_port):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            start = time.monotonic()
            try:
                sock.connect((host, port))
                elapsed = (time.monotonic() - start) * 1000
                connect_times.append(elapsed)
                port_success += 1
                sockets.append(sock)
            except (socket.timeout, ConnectionRefusedError, OSError):
                elapsed = (time.monotonic() - start) * 1000
                connect_times.append(elapsed)
                port_fail += 1
                sock.close()

        for sock in sockets:
            try:
                sock.close()
            except OSError:
                pass

        avg_time = sum(connect_times) / len(connect_times) if connect_times else 0
        total_time += sum(connect_times)
        total_success += port_success
        total_fail += port_fail

        results["port_results"][str(port)] = {
            "attempted": conns_per_port,
            "successful": port_success,
            "failed": port_fail,
            "avg_connect_time_ms": round(avg_time, 2),
        }

    total_attempted = total_success + total_fail
    results["successful_connections"] = total_success
    results["failed_connections"] = total_fail
    results["avg_connect_time_ms"] = round(
        total_time / total_attempted if total_attempted > 0 else 0, 2
    )

    return results


def run_latency_under_load_test(host: str, duration: int = 10) -> dict:
    """Measure latency changes while generating network load.

    Sends pings while simultaneously opening/closing connections
    to see how latency degrades under stress.
    """
    baseline_ping = run_ping_test(host, count=5)

    loaded_pings: list[float] = []
    end_time = time.monotonic() + duration

    while time.monotonic() < end_time:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        start = time.monotonic()
        try:
            sock.connect((host, 80))
            elapsed = (time.monotonic() - start) * 1000
            loaded_pings.append(elapsed)
            sock.close()
        except (socket.timeout, ConnectionRefusedError, OSError):
            elapsed = (time.monotonic() - start) * 1000
            loaded_pings.append(elapsed)
            try:
                sock.close()
            except OSError:
                pass

    loaded_avg = sum(loaded_pings) / len(loaded_pings) if loaded_pings else 0
    loaded_max = max(loaded_pings) if loaded_pings else 0
    loaded_min = min(loaded_pings) if loaded_pings else 0

    degradation = (
        ((loaded_avg - baseline_ping.avg_ms) / baseline_ping.avg_ms * 100)
        if baseline_ping.avg_ms > 0 else 0
    )

    return {
        "host": host,
        "duration_seconds": duration,
        "baseline_latency_ms": baseline_ping.avg_ms,
        "loaded_latency_avg_ms": round(loaded_avg, 2),
        "loaded_latency_min_ms": round(loaded_min, 2),
        "loaded_latency_max_ms": round(loaded_max, 2),
        "latency_degradation_percent": round(degradation, 2),
        "samples": len(loaded_pings),
        "loaded_jitter_ms": round(loaded_max - loaded_min, 2),
    }


def run_bandwidth_estimate_test(host: str) -> dict:
    """Estimate available bandwidth by measuring data transfer rates.

    Uses large ICMP packets to estimate throughput capacity.
    """
    packet_sizes = [64, 256, 512, 1024, 1400]
    results_list = []

    for size in packet_sizes:
        system = platform.system()
        try:
            if system == "Windows":
                cmd = ["ping", "-n", "5", "-l", str(size), host]
            else:
                cmd = ["ping", "-c", "5", "-s", str(size), host]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            parsed = _parse_ping_output(result.stdout, 5)

            if parsed["avg_ms"] > 0:
                throughput_kbps = (size * 8) / parsed["avg_ms"]
                results_list.append({
                    "packet_size": size,
                    "avg_latency_ms": parsed["avg_ms"],
                    "estimated_throughput_kbps": round(throughput_kbps, 2),
                })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    max_throughput = max(
        (r["estimated_throughput_kbps"] for r in results_list), default=0
    )

    return {
        "host": host,
        "packet_tests": results_list,
        "estimated_max_throughput_kbps": round(max_throughput, 2),
        "estimated_max_throughput_mbps": round(max_throughput / 1000, 2),
    }


def calculate_resilience_score(
    ping_result: PingResult,
    rapid_ping: PingResult,
    connection_test: dict,
    latency_load: dict,
) -> StressTestResult:
    """Calculate an overall network resilience score (0-100)."""
    scores = []

    # Ping quality (25 points)
    if ping_result.avg_ms <= 5:
        ping_score = 25
    elif ping_result.avg_ms <= 15:
        ping_score = 20
    elif ping_result.avg_ms <= 30:
        ping_score = 15
    elif ping_result.avg_ms <= 50:
        ping_score = 10
    else:
        ping_score = 5
    scores.append(ping_score)

    # Packet loss (25 points)
    if ping_result.loss_percent == 0:
        loss_score = 25
    elif ping_result.loss_percent <= 1:
        loss_score = 20
    elif ping_result.loss_percent <= 5:
        loss_score = 15
    elif ping_result.loss_percent <= 10:
        loss_score = 10
    else:
        loss_score = 5
    scores.append(loss_score)

    # Rapid ping stability (25 points)
    if rapid_ping.loss_percent == 0 and rapid_ping.jitter_ms < 5:
        rapid_score = 25
    elif rapid_ping.loss_percent <= 2 and rapid_ping.jitter_ms < 15:
        rapid_score = 20
    elif rapid_ping.loss_percent <= 5:
        rapid_score = 15
    elif rapid_ping.loss_percent <= 10:
        rapid_score = 10
    else:
        rapid_score = 5
    scores.append(rapid_score)

    # Latency under load (25 points)
    degradation = abs(latency_load.get("latency_degradation_percent", 100))
    if degradation <= 10:
        load_score = 25
    elif degradation <= 25:
        load_score = 20
    elif degradation <= 50:
        load_score = 15
    elif degradation <= 100:
        load_score = 10
    else:
        load_score = 5
    scores.append(load_score)

    total = sum(scores)

    if total >= 90:
        grade = "A+"
    elif total >= 80:
        grade = "A"
    elif total >= 70:
        grade = "B+"
    elif total >= 60:
        grade = "B"
    elif total >= 50:
        grade = "C"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    return StressTestResult(
        test_type="full_resilience",
        timestamp=datetime.utcnow().isoformat(),
        duration_seconds=0,
        score=total,
        grade=grade,
        details={
            "ping_quality_score": ping_score,
            "packet_loss_score": loss_score,
            "rapid_ping_score": rapid_score,
            "load_resilience_score": load_score,
            "breakdown": {
                "avg_latency_ms": ping_result.avg_ms,
                "packet_loss_pct": ping_result.loss_percent,
                "jitter_ms": ping_result.jitter_ms,
                "rapid_loss_pct": rapid_ping.loss_percent,
                "rapid_jitter_ms": rapid_ping.jitter_ms,
                "latency_degradation_pct": degradation,
            },
        },
    )


async def run_full_stress_test(host: str | None = None) -> dict:
    """Run the complete stress test suite against the gateway."""
    if not host:
        host = get_default_gateway() or "192.168.1.1"

    start_time = time.monotonic()
    results: dict = {"host": host, "tests": {}, "timestamp": datetime.utcnow().isoformat()}

    loop = asyncio.get_event_loop()

    # 1. Basic ping
    ping_result = await loop.run_in_executor(None, run_ping_test, host, 20)
    results["tests"]["ping"] = asdict(ping_result)

    # 2. Rapid ping
    rapid_ping = await loop.run_in_executor(None, run_rapid_ping_test, host, 50)
    results["tests"]["rapid_ping"] = asdict(rapid_ping)

    # 3. Concurrent connections
    conn_test = await loop.run_in_executor(
        None, run_concurrent_connection_test, host, 60
    )
    results["tests"]["concurrent_connections"] = conn_test

    # 4. Latency under load
    latency_load = await loop.run_in_executor(
        None, run_latency_under_load_test, host, 8
    )
    results["tests"]["latency_under_load"] = latency_load

    # 5. Bandwidth estimate
    bandwidth = await loop.run_in_executor(None, run_bandwidth_estimate_test, host)
    results["tests"]["bandwidth"] = bandwidth

    # 6. Overall score
    score_result = calculate_resilience_score(
        ping_result, rapid_ping, conn_test, latency_load
    )
    elapsed = time.monotonic() - start_time
    score_result.duration_seconds = round(elapsed, 2)
    results["score"] = asdict(score_result)
    results["duration_seconds"] = round(elapsed, 2)

    return results
