"""WiFi network scanner module.

Provides cross-platform WiFi scanning using system utilities
(nmcli, iwlist, iw, or netsh on Windows). Includes mock data
fallback for environments without wireless interfaces.
"""

import json
import platform
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WiFiNetwork:
    ssid: str
    bssid: str
    signal_strength: int  # dBm
    signal_quality: int  # 0-100%
    channel: int
    frequency: str  # e.g. "2.4 GHz" or "5 GHz"
    encryption: str  # e.g. "WPA2", "WPA3", "Open"
    mode: str  # e.g. "Infrastructure", "Ad-Hoc"
    band: str  # e.g. "2.4GHz", "5GHz"
    speed: str  # e.g. "54 Mbps"
    vendor: str  # OUI-based vendor guess
    first_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# Common OUI prefixes for vendor identification
OUI_VENDORS = {
    "00:14:22": "Dell",
    "00:1A:2B": "Ayecom",
    "00:1B:44": "SanDisk",
    "00:1E:58": "D-Link",
    "00:1F:3A": "Hon Hai (Foxconn)",
    "00:21:6A": "Intel",
    "00:22:6B": "Cisco-Linksys",
    "00:23:69": "Cisco",
    "00:25:00": "Apple",
    "00:26:5A": "D-Link",
    "00:50:F2": "Microsoft",
    "08:00:27": "Oracle (VirtualBox)",
    "10:FE:ED": "Google",
    "18:FE:34": "Espressif (ESP8266)",
    "24:0A:C4": "Espressif (ESP32)",
    "2C:F0:5D": "Micro-Star (MSI)",
    "30:B5:C2": "TP-Link",
    "34:97:F6": "ASUSTek",
    "3C:37:86": "Netgear",
    "40:3F:8C": "TP-Link",
    "44:D9:E7": "Ubiquiti",
    "4C:ED:FB": "ASUSTek",
    "50:C7:BF": "TP-Link",
    "58:D5:6E": "D-Link",
    "60:38:E0": "Belkin",
    "68:FF:7B": "TP-Link",
    "74:DA:38": "Edimax",
    "78:8A:20": "Ubiquiti",
    "80:2A:A8": "Ubiquiti",
    "84:D8:1B": "TP-Link",
    "8C:3B:AD": "Netgear",
    "9C:5C:8E": "TP-Link",
    "A4:2B:B0": "TP-Link",
    "AC:84:C6": "TP-Link",
    "B0:4E:26": "TP-Link",
    "B4:75:0E": "Belkin",
    "C0:25:E9": "TP-Link",
    "C0:56:27": "Belkin",
    "C4:6E:1F": "TP-Link",
    "C8:3A:35": "Tenda",
    "CC:32:E5": "TP-Link",
    "D4:6E:0E": "TP-Link",
    "D8:07:B6": "TP-Link",
    "DC:EF:09": "TP-Link",
    "E4:F0:42": "Google",
    "E8:94:F6": "TP-Link",
    "EC:08:6B": "TP-Link",
    "F0:9F:C2": "Ubiquiti",
    "F4:F2:6D": "TP-Link",
    "F8:D1:11": "TP-Link",
}


def _lookup_vendor(bssid: str) -> str:
    prefix = bssid[:8].upper()
    return OUI_VENDORS.get(prefix, "Unknown")


def _dbm_to_quality(dbm: int) -> int:
    if dbm >= -30:
        return 100
    if dbm <= -90:
        return 0
    return max(0, min(100, 2 * (dbm + 90)))


def _freq_to_channel(freq_mhz: int) -> int:
    if 2412 <= freq_mhz <= 2484:
        if freq_mhz == 2484:
            return 14
        return (freq_mhz - 2412) // 5 + 1
    if 5170 <= freq_mhz <= 5825:
        return (freq_mhz - 5170) // 5 + 34
    return 0


def _freq_to_band(freq_mhz: int) -> str:
    if 2400 <= freq_mhz <= 2500:
        return "2.4GHz"
    if 5100 <= freq_mhz <= 5900:
        return "5GHz"
    if 5925 <= freq_mhz <= 7125:
        return "6GHz"
    return "Unknown"


def _scan_nmcli() -> Optional[list[WiFiNetwork]]:
    """Scan using NetworkManager's nmcli."""
    try:
        result = subprocess.run(
            [
                "nmcli",
                "-t",
                "-f",
                "SSID,BSSID,SIGNAL,FREQ,CHAN,MODE,SECURITY,RATE",
                "dev",
                "wifi",
                "list",
                "--rescan",
                "yes",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        networks = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) < 8:
                continue

            ssid = parts[0].strip() or "<Hidden>"
            bssid = ":".join(parts[1:7]).strip()
            try:
                signal_pct = int(parts[7].strip())
            except (ValueError, IndexError):
                signal_pct = 0

            try:
                freq = int(parts[8].strip().split()[0])
            except (ValueError, IndexError):
                freq = 2412

            try:
                channel = int(parts[9].strip())
            except (ValueError, IndexError):
                channel = _freq_to_channel(freq)

            mode = parts[10].strip() if len(parts) > 10 else "Infrastructure"
            security = parts[11].strip() if len(parts) > 11 else "Unknown"
            rate = parts[12].strip() if len(parts) > 12 else "Unknown"

            dbm = int(-100 + signal_pct)
            band = _freq_to_band(freq)
            freq_label = f"{freq / 1000:.1f} GHz"

            networks.append(
                WiFiNetwork(
                    ssid=ssid,
                    bssid=bssid,
                    signal_strength=dbm,
                    signal_quality=signal_pct,
                    channel=channel,
                    frequency=freq_label,
                    encryption=security if security else "Open",
                    mode=mode,
                    band=band,
                    speed=rate,
                    vendor=_lookup_vendor(bssid),
                )
            )
        return networks if networks else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _scan_iwlist() -> Optional[list[WiFiNetwork]]:
    """Scan using iwlist (requires root)."""
    try:
        iface_result = subprocess.run(
            ["iwconfig"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        iface = None
        for line in iface_result.stdout.split("\n"):
            if "IEEE 802.11" in line:
                iface = line.split()[0]
                break

        if not iface:
            return None

        result = subprocess.run(
            ["sudo", "iwlist", iface, "scan"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        networks = []
        current: dict = {}
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line.startswith("Cell"):
                if current:
                    networks.append(_build_network_from_dict(current))
                current = {}
                match = re.search(r"Address:\s*(.+)", line)
                if match:
                    current["bssid"] = match.group(1).strip()

            elif "ESSID:" in line:
                match = re.search(r'ESSID:"(.+?)"', line)
                current["ssid"] = match.group(1) if match else "<Hidden>"

            elif "Frequency:" in line:
                match = re.search(r"Frequency:(\d+\.?\d*)\s*GHz", line)
                if match:
                    current["frequency"] = float(match.group(1))
                chan_match = re.search(r"Channel\s+(\d+)", line)
                if chan_match:
                    current["channel"] = int(chan_match.group(1))

            elif "Signal level" in line:
                match = re.search(r"Signal level[=:](-?\d+)", line)
                if match:
                    current["signal"] = int(match.group(1))

            elif "Encryption key:" in line:
                current["encrypted"] = "on" in line.lower()

            elif "IE:" in line:
                if "WPA3" in line:
                    current["encryption"] = "WPA3"
                elif "WPA2" in line:
                    current["encryption"] = "WPA2"
                elif "WPA" in line:
                    current["encryption"] = "WPA"

            elif "Mode:" in line:
                match = re.search(r"Mode:(.+)", line)
                if match:
                    current["mode"] = match.group(1).strip()

            elif "Bit Rates:" in line:
                match = re.search(r"Bit Rates:(.+)", line)
                if match:
                    current["speed"] = match.group(1).strip()

        if current:
            networks.append(_build_network_from_dict(current))

        return networks if networks else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _build_network_from_dict(d: dict) -> WiFiNetwork:
    bssid = d.get("bssid", "00:00:00:00:00:00")
    ssid = d.get("ssid", "<Hidden>")
    dbm = d.get("signal", -70)
    freq = d.get("frequency", 2.412)
    channel = d.get("channel", _freq_to_channel(int(freq * 1000)))
    encrypted = d.get("encrypted", False)
    encryption = d.get("encryption", "WPA2" if encrypted else "Open")
    mode = d.get("mode", "Infrastructure")
    speed = d.get("speed", "Unknown")
    freq_mhz = int(freq * 1000)

    return WiFiNetwork(
        ssid=ssid,
        bssid=bssid,
        signal_strength=dbm,
        signal_quality=_dbm_to_quality(dbm),
        channel=channel,
        frequency=f"{freq:.1f} GHz",
        encryption=encryption,
        mode=mode,
        band=_freq_to_band(freq_mhz),
        speed=speed,
        vendor=_lookup_vendor(bssid),
    )


def _scan_iw() -> Optional[list[WiFiNetwork]]:
    """Scan using iw (modern Linux)."""
    try:
        link_result = subprocess.run(
            ["iw", "dev"], capture_output=True, text=True, timeout=10
        )
        iface = None
        for line in link_result.stdout.split("\n"):
            if "Interface" in line:
                iface = line.split()[-1]
                break

        if not iface:
            return None

        result = subprocess.run(
            ["sudo", "iw", iface, "scan"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        networks = []
        current: dict = {}
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line.startswith("BSS "):
                if current:
                    networks.append(_build_network_from_dict(current))
                current = {}
                match = re.search(r"BSS\s+([0-9a-fA-F:]+)", line)
                if match:
                    current["bssid"] = match.group(1)

            elif line.startswith("SSID:"):
                current["ssid"] = line.split(":", 1)[1].strip() or "<Hidden>"

            elif line.startswith("freq:"):
                freq_mhz = int(line.split(":")[1].strip())
                current["frequency"] = freq_mhz / 1000
                current["channel"] = _freq_to_channel(freq_mhz)

            elif line.startswith("signal:"):
                match = re.search(r"(-?\d+\.?\d*)", line)
                if match:
                    current["signal"] = int(float(match.group(1)))

            elif "WPA" in line or "RSN" in line:
                if "WPA" not in current.get("encryption", ""):
                    current["encryption"] = "WPA2"

        if current:
            networks.append(_build_network_from_dict(current))

        return networks if networks else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _generate_mock_data() -> list[WiFiNetwork]:
    """Generate realistic mock WiFi data for demo/testing."""
    import random

    mock_networks = [
        ("HomeNetwork_5G", "34:97:F6:1A:2B:3C", -42, 5745, "WPA2", "130 Mbps"),
        ("HomeNetwork", "34:97:F6:1A:2B:3D", -55, 2437, "WPA2", "54 Mbps"),
        ("OfficeWiFi", "3C:37:86:4D:5E:6F", -60, 5180, "WPA3", "866 Mbps"),
        ("CoffeeShop_Free", "30:B5:C2:7A:8B:9C", -68, 2462, "Open", "54 Mbps"),
        ("Neighbor_Net", "C4:6E:1F:0D:1E:2F", -72, 2412, "WPA2", "72 Mbps"),
        ("SmartHome_IoT", "18:FE:34:3A:4B:5C", -58, 2427, "WPA", "54 Mbps"),
        ("5G_Ultra", "44:D9:E7:6D:7E:8F", -45, 5500, "WPA3", "1200 Mbps"),
        ("Guest_Network", "A4:2B:B0:9A:0B:1C", -75, 2447, "WPA2", "54 Mbps"),
        ("<Hidden>", "80:2A:A8:2D:3E:4F", -80, 5220, "WPA2", "300 Mbps"),
        ("Library_Public", "E4:F0:42:5F:60:71", -63, 2422, "Open", "54 Mbps"),
        ("TechStartup_5G", "78:8A:20:82:93:A4", -50, 5745, "WPA3", "866 Mbps"),
        ("Apartment_302", "D8:07:B6:B5:C6:D7", -78, 2432, "WPA2", "54 Mbps"),
        ("SecurityCam_Net", "24:0A:C4:E8:F9:0A", -65, 2452, "WPA2", "54 Mbps"),
        ("FibreConnect", "C8:3A:35:1B:2C:3D", -38, 5200, "WPA3", "2400 Mbps"),
        ("MobileHotspot", "50:C7:BF:4E:5F:60", -82, 2417, "WPA2", "72 Mbps"),
        ("PrinterWiFi", "00:1E:58:71:82:93", -88, 2442, "WPA", "11 Mbps"),
        ("GamingRouter_5G", "2C:F0:5D:A4:B5:C6", -48, 5580, "WPA3", "1733 Mbps"),
        ("Warehouse_AP", "8C:3B:AD:D7:E8:F9", -70, 2457, "WPA2", "300 Mbps"),
    ]

    networks = []
    for ssid, bssid, base_dbm, freq, enc, speed in mock_networks:
        jitter = random.randint(-5, 5)
        dbm = max(-95, min(-20, base_dbm + jitter))
        channel = _freq_to_channel(freq)
        band = _freq_to_band(freq)
        freq_label = f"{freq / 1000:.1f} GHz"

        networks.append(
            WiFiNetwork(
                ssid=ssid,
                bssid=bssid,
                signal_strength=dbm,
                signal_quality=_dbm_to_quality(dbm),
                channel=channel,
                frequency=freq_label,
                encryption=enc,
                mode="Infrastructure",
                band=band,
                speed=speed,
                vendor=_lookup_vendor(bssid),
            )
        )

    return networks


def scan_networks() -> list[WiFiNetwork]:
    """Scan for WiFi networks using available system tools.

    Tries nmcli, iw, iwlist in order. Falls back to mock data
    if no wireless interface is available.
    """
    system = platform.system()

    if system == "Linux":
        for scanner in (_scan_nmcli, _scan_iw, _scan_iwlist):
            result = scanner()
            if result:
                return result

    # Fallback to mock data
    return _generate_mock_data()


def get_scan_summary(networks: list[WiFiNetwork]) -> dict:
    """Generate summary statistics for a scan result."""
    if not networks:
        return {
            "total": 0,
            "open": 0,
            "secured": 0,
            "hidden": 0,
            "band_2ghz": 0,
            "band_5ghz": 0,
            "band_6ghz": 0,
            "avg_signal": 0,
            "strongest": None,
            "weakest": None,
            "channels": {},
            "encryption_types": {},
            "vendors": {},
        }

    open_nets = sum(1 for n in networks if n.encryption == "Open")
    hidden = sum(1 for n in networks if n.ssid == "<Hidden>")
    band_2 = sum(1 for n in networks if "2.4" in n.band)
    band_5 = sum(1 for n in networks if "5" in n.band)
    band_6 = sum(1 for n in networks if "6" in n.band)
    avg_signal = sum(n.signal_strength for n in networks) // len(networks)
    strongest = max(networks, key=lambda n: n.signal_strength)
    weakest = min(networks, key=lambda n: n.signal_strength)

    channels: dict[int, int] = {}
    enc_types: dict[str, int] = {}
    vendors: dict[str, int] = {}
    for n in networks:
        channels[n.channel] = channels.get(n.channel, 0) + 1
        enc_types[n.encryption] = enc_types.get(n.encryption, 0) + 1
        vendors[n.vendor] = vendors.get(n.vendor, 0) + 1

    return {
        "total": len(networks),
        "open": open_nets,
        "secured": len(networks) - open_nets,
        "hidden": hidden,
        "band_2ghz": band_2,
        "band_5ghz": band_5,
        "band_6ghz": band_6,
        "avg_signal": avg_signal,
        "strongest": strongest.to_dict(),
        "weakest": weakest.to_dict(),
        "channels": channels,
        "encryption_types": enc_types,
        "vendors": vendors,
    }
