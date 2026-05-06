"""WiFi Bandwidth Manager Module.

Discovers connected devices on the local network and provides
bandwidth/speed control using Linux Traffic Control (tc).
Includes device discovery via ARP scanning and per-device
speed limit management.
"""

import platform
import re
import socket
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime


# Throttle mode labels
THROTTLE_MODES = {
    "slow": {"download_kbps": 128, "upload_kbps": 64, "label": "Slow (128/64 Kbps)"},
    "very_slow": {"download_kbps": 32, "upload_kbps": 16, "label": "Very Slow (32/16 Kbps)"},
    "pause": {"download_kbps": 1, "upload_kbps": 1, "label": "Paused (1/1 Kbps)"},
    "custom": {"download_kbps": 0, "upload_kbps": 0, "label": "Custom"},
}


@dataclass
class ConnectedDevice:
    ip: str
    mac: str
    hostname: str
    vendor: str
    status: str  # "online" / "offline"
    speed_limit_down: int  # Kbps, 0 = unlimited
    speed_limit_up: int  # Kbps, 0 = unlimited
    throttle_mode: str = ""  # "", "slow", "very_slow", "pause"
    throttle_expires: str = ""  # ISO timestamp when throttle auto-expires
    first_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_throttled"] = self.throttle_mode != ""
        d["throttle_label"] = THROTTLE_MODES.get(self.throttle_mode, {}).get("label", "Unlimited")
        return d


# In-memory device registry and speed rules
device_registry: dict[str, ConnectedDevice] = {}
speed_rules: dict[str, dict] = {}

# OUI vendor lookup (subset)
OUI_VENDORS = {
    "00:25:00": "Apple",
    "3C:22:FB": "Apple",
    "A4:83:E7": "Apple",
    "F0:18:98": "Apple",
    "AC:DE:48": "Apple",
    "34:97:F6": "ASUS",
    "30:B5:C2": "TP-Link",
    "C4:6E:1F": "TP-Link",
    "50:C7:BF": "TP-Link",
    "10:FE:ED": "Google",
    "E4:F0:42": "Google",
    "00:50:F2": "Microsoft",
    "3C:37:86": "Netgear",
    "44:D9:E7": "Ubiquiti",
    "18:FE:34": "Espressif (ESP)",
    "24:0A:C4": "Espressif (ESP)",
    "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "00:1A:79": "Samsung",
    "C0:97:27": "Samsung",
    "94:65:2D": "OnePlus",
    "2C:F0:5D": "MSI",
    "00:21:6A": "Intel",
    "7C:B0:C2": "Intel",
    "F4:8C:50": "Intel",
    "00:1E:58": "D-Link",
    "28:6C:07": "Xiaomi",
    "64:CE:D1": "Xiaomi",
    "78:11:DC": "Xiaomi",
    "9C:28:EF": "Huawei",
    "48:46:FB": "Huawei",
    "04:F1:28": "Huawei",
    "A0:C5:89": "LG",
    "00:0E:8F": "Cisco",
    "00:22:6B": "Cisco-Linksys",
}


def _lookup_vendor(mac: str) -> str:
    prefix = mac[:8].upper()
    return OUI_VENDORS.get(prefix, "Unknown")


def _resolve_hostname(ip: str) -> str:
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


def discover_devices() -> list[ConnectedDevice]:
    """Discover connected devices on the local network via ARP."""
    devices = []
    system = platform.system()

    if system == "Linux":
        devices = _discover_arp_linux()

    if not devices:
        devices = _generate_mock_devices()

    # Update registry
    now = datetime.utcnow().isoformat()
    for dev in devices:
        if dev.mac in device_registry:
            existing = device_registry[dev.mac]
            dev.speed_limit_down = existing.speed_limit_down
            dev.speed_limit_up = existing.speed_limit_up
            dev.throttle_mode = existing.throttle_mode
            dev.throttle_expires = existing.throttle_expires
            dev.first_seen = existing.first_seen
        dev.last_seen = now
        device_registry[dev.mac] = dev

    return devices


def _discover_arp_linux() -> list[ConnectedDevice]:
    """Discover devices using arp and ip neigh on Linux."""
    devices = []
    seen_macs: set[str] = set()

    # Try ip neigh
    try:
        result = subprocess.run(
            ["ip", "neigh", "show"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 5 and "lladdr" in parts:
                ip = parts[0]
                mac_idx = parts.index("lladdr") + 1
                mac = parts[mac_idx].upper()
                state = parts[-1] if parts[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE") else "STALE"

                if mac in seen_macs or mac == "00:00:00:00:00:00":
                    continue
                seen_macs.add(mac)

                hostname = _resolve_hostname(ip)
                vendor = _lookup_vendor(mac)
                status = "online" if state in ("REACHABLE", "DELAY", "PROBE") else "online"

                existing = device_registry.get(mac)
                devices.append(ConnectedDevice(
                    ip=ip,
                    mac=mac,
                    hostname=hostname,
                    vendor=vendor,
                    status=status,
                    speed_limit_down=existing.speed_limit_down if existing else 0,
                    speed_limit_up=existing.speed_limit_up if existing else 0,
                ))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try arp -a as fallback
    if not devices:
        try:
            result = subprocess.run(
                ["arp", "-a"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                match = re.search(
                    r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]+)",
                    line,
                )
                if match:
                    ip = match.group(1)
                    mac = match.group(2).upper()
                    if mac in seen_macs or mac == "00:00:00:00:00:00":
                        continue
                    seen_macs.add(mac)

                    hostname_match = re.match(r"(\S+)\s+\(", line)
                    hostname = hostname_match.group(1) if hostname_match and hostname_match.group(1) != "?" else _resolve_hostname(ip)
                    vendor = _lookup_vendor(mac)

                    existing = device_registry.get(mac)
                    devices.append(ConnectedDevice(
                        ip=ip,
                        mac=mac,
                        hostname=hostname,
                        vendor=vendor,
                        status="online",
                        speed_limit_down=existing.speed_limit_down if existing else 0,
                        speed_limit_up=existing.speed_limit_up if existing else 0,
                    ))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return devices


def _generate_mock_devices() -> list[ConnectedDevice]:
    """Generate mock connected devices for demo purposes."""
    import random

    mock_devices = [
        ("192.168.1.1", "30:B5:C2:AA:BB:CC", "router.local", "TP-Link"),
        ("192.168.1.10", "A4:83:E7:11:22:33", "iPhone-Kumar", "Apple"),
        ("192.168.1.11", "C0:97:27:44:55:66", "Galaxy-S24", "Samsung"),
        ("192.168.1.12", "7C:B0:C2:77:88:99", "Kumar-Laptop", "Intel"),
        ("192.168.1.13", "28:6C:07:AA:BB:DD", "Redmi-Note", "Xiaomi"),
        ("192.168.1.14", "B8:27:EB:CC:DD:EE", "RaspberryPi", "Raspberry Pi"),
        ("192.168.1.15", "94:65:2D:11:22:FF", "OnePlus-9", "OnePlus"),
        ("192.168.1.16", "18:FE:34:55:66:77", "Smart-Light", "Espressif (ESP)"),
        ("192.168.1.17", "DC:A6:32:88:99:AA", "Pi-Camera", "Raspberry Pi"),
        ("192.168.1.18", "48:46:FB:BB:CC:DD", "Huawei-Tab", "Huawei"),
        ("192.168.1.20", "3C:22:FB:EE:FF:00", "MacBook-Pro", "Apple"),
        ("192.168.1.21", "00:50:F2:11:22:33", "Windows-PC", "Microsoft"),
    ]

    devices = []
    for ip, mac, hostname, vendor in mock_devices:
        existing = device_registry.get(mac)
        devices.append(ConnectedDevice(
            ip=ip,
            mac=mac,
            hostname=hostname,
            vendor=vendor,
            status=random.choice(["online", "online", "online", "offline"]),
            speed_limit_down=existing.speed_limit_down if existing else 0,
            speed_limit_up=existing.speed_limit_up if existing else 0,
        ))

    return devices


def set_speed_limit(mac: str, download_kbps: int, upload_kbps: int) -> dict:
    """Set bandwidth speed limit for a device.

    Uses Linux tc (traffic control) for actual enforcement.
    Falls back to storing the rule in memory for demo mode.

    Args:
        mac: Device MAC address
        download_kbps: Download speed limit in Kbps (0 = unlimited)
        upload_kbps: Upload speed limit in Kbps (0 = unlimited)

    Returns:
        Status dict with result info
    """
    mac = mac.upper()

    if mac not in device_registry:
        return {"status": "error", "message": f"Device {mac} not found. Run device discovery first."}

    device = device_registry[mac]
    device.speed_limit_down = download_kbps
    device.speed_limit_up = upload_kbps

    speed_rules[mac] = {
        "mac": mac,
        "ip": device.ip,
        "download_kbps": download_kbps,
        "upload_kbps": upload_kbps,
        "applied_at": datetime.utcnow().isoformat(),
    }

    # Try to apply via tc on Linux
    tc_result = _apply_tc_rule(device.ip, download_kbps, upload_kbps)

    dl_label = f"{download_kbps} Kbps" if download_kbps > 0 else "Unlimited"
    ul_label = f"{upload_kbps} Kbps" if upload_kbps > 0 else "Unlimited"

    return {
        "status": "success",
        "mac": mac,
        "ip": device.ip,
        "hostname": device.hostname,
        "download_limit": dl_label,
        "upload_limit": ul_label,
        "tc_applied": tc_result.get("applied", False),
        "message": f"Speed limit set: Down={dl_label}, Up={ul_label}",
    }


def remove_speed_limit(mac: str) -> dict:
    """Remove speed limit for a device."""
    mac = mac.upper()

    if mac in device_registry:
        device = device_registry[mac]
        device.speed_limit_down = 0
        device.speed_limit_up = 0

    if mac in speed_rules:
        ip = speed_rules[mac]["ip"]
        del speed_rules[mac]
        _remove_tc_rule(ip)

    return {
        "status": "success",
        "mac": mac,
        "message": "Speed limit removed",
    }


def get_all_rules() -> list[dict]:
    """Get all active speed rules."""
    return list(speed_rules.values())


def get_device_list() -> list[dict]:
    """Get all known devices with their current speed limits."""
    return [dev.to_dict() for dev in device_registry.values()]


def _apply_tc_rule(ip: str, download_kbps: int, upload_kbps: int) -> dict:
    """Apply traffic control rule using tc on Linux.

    This uses HTB (Hierarchical Token Bucket) qdisc for rate limiting.
    Requires root privileges.
    """
    if platform.system() != "Linux":
        return {"applied": False, "reason": "Not Linux"}

    if download_kbps == 0 and upload_kbps == 0:
        _remove_tc_rule(ip)
        return {"applied": True, "reason": "Removed (unlimited)"}

    try:
        # Get the main network interface
        iface = _get_main_interface()
        if not iface:
            return {"applied": False, "reason": "No interface found"}

        # Generate a unique class id from IP
        ip_parts = ip.split(".")
        class_id = int(ip_parts[-1]) + 10  # offset to avoid conflicts

        if download_kbps > 0:
            rate = f"{download_kbps}kbit"

            # Check if root qdisc exists
            check = subprocess.run(
                ["tc", "qdisc", "show", "dev", iface],
                capture_output=True, text=True, timeout=5,
            )

            if "htb" not in check.stdout:
                subprocess.run(
                    ["sudo", "tc", "qdisc", "add", "dev", iface, "root",
                     "handle", "1:", "htb", "default", "999"],
                    capture_output=True, text=True, timeout=5,
                )
                subprocess.run(
                    ["sudo", "tc", "class", "add", "dev", iface, "parent",
                     "1:", "classid", "1:999", "htb", "rate", "1000mbit"],
                    capture_output=True, text=True, timeout=5,
                )

            # Remove existing class for this IP
            subprocess.run(
                ["sudo", "tc", "class", "del", "dev", iface, "parent",
                 "1:", "classid", f"1:{class_id}"],
                capture_output=True, text=True, timeout=5,
            )

            # Add class with rate limit
            subprocess.run(
                ["sudo", "tc", "class", "add", "dev", iface, "parent",
                 "1:", "classid", f"1:{class_id}", "htb",
                 "rate", rate, "ceil", rate],
                capture_output=True, text=True, timeout=5,
            )

            # Add filter to match IP
            subprocess.run(
                ["sudo", "tc", "filter", "add", "dev", iface, "parent",
                 "1:", "protocol", "ip", "prio", "1", "u32",
                 "match", "ip", "dst", f"{ip}/32", "flowid", f"1:{class_id}"],
                capture_output=True, text=True, timeout=5,
            )

        return {"applied": True, "reason": "tc rules applied"}

    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError) as e:
        return {"applied": False, "reason": str(e)}


def _remove_tc_rule(ip: str) -> dict:
    """Remove tc rule for a specific IP."""
    if platform.system() != "Linux":
        return {"removed": False}

    try:
        iface = _get_main_interface()
        if not iface:
            return {"removed": False}

        ip_parts = ip.split(".")
        class_id = int(ip_parts[-1]) + 10

        subprocess.run(
            ["sudo", "tc", "class", "del", "dev", iface, "parent",
             "1:", "classid", f"1:{class_id}"],
            capture_output=True, text=True, timeout=5,
        )
        return {"removed": True}
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        return {"removed": False}


def _get_main_interface() -> str | None:
    """Get the main network interface name."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r"dev\s+(\S+)", result.stdout)
        if match:
            return match.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# Timer registry for auto-restore
_active_timers: dict[str, threading.Timer] = {}


def throttle_device(mac: str, mode: str, duration_seconds: int = 0) -> dict:
    """Quick throttle a device.

    Modes: slow (128/64), very_slow (32/16), pause (1/1)
    If duration_seconds > 0, auto-restores after that time.
    """
    mac = mac.upper()

    if mac not in device_registry:
        return {"status": "error", "message": f"Device {mac} not found. Run discovery first."}

    if mode not in THROTTLE_MODES:
        return {"status": "error", "message": f"Invalid mode. Use: {', '.join(THROTTLE_MODES.keys())}"}

    preset = THROTTLE_MODES[mode]
    device = device_registry[mac]

    result = set_speed_limit(mac, preset["download_kbps"], preset["upload_kbps"])
    if result["status"] != "success":
        return result

    device.throttle_mode = mode
    expires = ""

    # Cancel any existing timer
    if mac in _active_timers:
        _active_timers[mac].cancel()
        del _active_timers[mac]

    # Set auto-restore timer if duration specified
    if duration_seconds > 0:
        from datetime import timedelta
        expire_time = datetime.utcnow() + timedelta(seconds=duration_seconds)
        expires = expire_time.isoformat()
        device.throttle_expires = expires

        timer = threading.Timer(duration_seconds, _auto_restore, args=[mac])
        timer.daemon = True
        timer.start()
        _active_timers[mac] = timer

    duration_label = f" for {_format_duration(duration_seconds)}" if duration_seconds > 0 else ""
    return {
        "status": "success",
        "mac": mac,
        "mode": mode,
        "label": preset["label"],
        "duration_seconds": duration_seconds,
        "expires": expires,
        "message": f"{device.hostname or device.ip} set to {preset['label']}{duration_label}",
    }


def _auto_restore(mac: str) -> None:
    """Auto-restore callback triggered by timer."""
    mac = mac.upper()
    if mac in device_registry:
        device = device_registry[mac]
        device.speed_limit_down = 0
        device.speed_limit_up = 0
        device.throttle_mode = ""
        device.throttle_expires = ""

    if mac in speed_rules:
        ip = speed_rules[mac]["ip"]
        del speed_rules[mac]
        _remove_tc_rule(ip)

    if mac in _active_timers:
        del _active_timers[mac]


def restore_device(mac: str) -> dict:
    """Immediately restore a device to full speed."""
    mac = mac.upper()

    # Cancel timer if exists
    if mac in _active_timers:
        _active_timers[mac].cancel()
        del _active_timers[mac]

    if mac in device_registry:
        device = device_registry[mac]
        device.throttle_mode = ""
        device.throttle_expires = ""

    result = remove_speed_limit(mac)
    result["message"] = "Device restored to full speed"
    return result


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"


def get_throttle_modes() -> list[dict]:
    """Get available throttle modes."""
    return [
        {"id": k, **v}
        for k, v in THROTTLE_MODES.items()
        if k != "custom"
    ]


def get_bandwidth_summary() -> dict:
    """Get summary of bandwidth management state."""
    total_devices = len(device_registry)
    online = sum(1 for d in device_registry.values() if d.status == "online")
    limited = sum(1 for d in device_registry.values() if d.speed_limit_down > 0 or d.speed_limit_up > 0)
    unlimited = total_devices - limited

    return {
        "total_devices": total_devices,
        "online_devices": online,
        "offline_devices": total_devices - online,
        "limited_devices": limited,
        "unlimited_devices": unlimited,
        "active_rules": len(speed_rules),
    }
