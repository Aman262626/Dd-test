# WiFi Scanner Pro

Advanced WiFi network discovery and analysis tool with a modern web-based dashboard. Scan, visualize, and analyze nearby WiFi networks with real-time updates and detailed analytics.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

### Core Scanning
- **Network Discovery** — Scan nearby WiFi networks using system tools (`nmcli`, `iw`, `iwlist`)
- **Rich Network Details** — SSID, BSSID, signal strength (dBm + quality %), channel, frequency, encryption, speed, vendor identification
- **Cross-Platform** — Works on Linux with automatic fallback to demo data for environments without wireless interfaces
- **OUI Vendor Lookup** — Identifies router manufacturers from MAC address prefixes

### Visualization & Analytics
- **Signal Strength Charts** — Bar chart showing signal levels across all discovered networks
- **Encryption Distribution** — Doughnut chart breaking down WPA2/WPA3/Open/WPA usage
- **Band Distribution** — Visual split between 2.4 GHz and 5 GHz networks
- **Vendor Distribution** — Horizontal bar chart of router manufacturers
- **Channel Congestion Analysis** — Separate views for 2.4 GHz and 5 GHz channel usage
- **Channel Recommendations** — Automatically suggests the least congested channels

### Extra Features
- **Auto-Refresh** — Configurable automatic scanning at 5s, 10s, 30s, or 60s intervals
- **Signal History Tracking** — Track signal strength changes over time for any network
- **Network Search** — Filter by SSID, BSSID, or vendor name
- **Band & Security Filters** — Filter by 2.4/5 GHz band or encryption type
- **Sortable Results** — Sort by signal strength, name, channel, or security
- **Export to CSV** — Download scan results as a CSV spreadsheet
- **Export to JSON** — Download raw scan data in JSON format
- **Scan History Log** — Table of all scans with timestamps and network counts
- **Network Detail Modal** — Click any network for a detailed view with signal gauge
- **Dark/Light Theme** — Toggle between dark and light modes with persistent preference
- **Responsive Design** — Works on desktop, tablet, and mobile screens
- **Toast Notifications** — Real-time feedback for scan events

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Vanilla JS, Chart.js 4.x |
| Styling | Custom CSS with CSS Variables |
| Templating | Jinja2 |
| Fonts | Inter, JetBrains Mono (Google Fonts) |

## Quick Start

### Prerequisites
- Python 3.10 or higher
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/Aman262626/Dd-test.git
cd Dd-test

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### Using a Virtual Environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
python app.py
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main web dashboard |
| `/api/scan` | GET | Perform WiFi scan, returns networks + summary |
| `/api/history` | GET | Get scan history (query: `?limit=20`) |
| `/api/network/{bssid}/history` | GET | Signal history for a specific network |
| `/api/export/csv` | GET | Download last scan as CSV |
| `/api/export/json` | GET | Download last scan as JSON |
| `/api/stats` | GET | Aggregated statistics across all scans |
| `/api/channel-analysis` | GET | Channel congestion analysis with recommendations |

## WiFi Scanning

The scanner tries multiple Linux tools in order:
1. **nmcli** (NetworkManager) — Most common on desktop Linux
2. **iw** — Modern Linux wireless tool
3. **iwlist** — Legacy wireless scanning (requires root)

If no wireless interface is detected (e.g., running in a VM, container, or on a server), the app automatically provides **realistic mock data** so you can still explore all dashboard features.

## Project Structure

```
Dd-test/
├── app.py              # FastAPI backend with REST API
├── scanner.py           # WiFi scanning module with system tool integration
├── requirements.txt     # Python dependencies
├── README.md            # This file
├── templates/
│   └── index.html       # Main dashboard template
└── static/
    ├── css/
    │   └── style.css    # Theme-aware responsive styles
    └── js/
        └── app.js       # Frontend application logic
```

## Screenshots

> Run the app and click "Scan Networks" to see the dashboard in action with network cards, charts, and analytics.

## License

MIT License — feel free to use, modify, and distribute.
