# Auto-Flyer (Windows Edition)

Windows-first utility for simulated iPhone GPS location on iOS 18+ using `pymobiledevice3`.

This release is focused on **Windows 10/11** and includes:

- `fly.py`: CLI for `set` / `route` / `clear` / `status` / `doctor`
- `webui.py`: local browser UI for all major workflows
- `geocode.py`: address-to-coordinate helper

This tool uses simulated location and does not permanently modify hardware GPS.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 (recommended for dependency compatibility)
- iPhone with iOS 18+
- iPhone trusted/paired with this PC
- Developer Mode enabled on iPhone
- Administrator PowerShell for tunnel startup
- Internet access for:
  - geocoding (Nominatim)
  - road routing (OSRM)

## Setup (Windows)

1. Clone the repository.

```powershell
git clone <your-repo-url>
cd Auto-Flyer
```

2. Create Python 3.11 virtual environment.

```powershell
uv venv .venv311 --python 3.11
```

3. Install dependencies.

```powershell
uv pip install -r requirements.txt --python .venv311\Scripts\python.exe
```

4. Open **PowerShell as Administrator**, then verify readiness.

```powershell
cd "C:\path\to\Auto-Flyer"
.venv311\Scripts\python.exe fly.py doctor
```

Look for:

- `windows_admin: yes`
- `pymobiledevice3: ok`
- `device_detect: >= 1`

## Quick Start

### CLI

Set fixed location:

```powershell
.venv311\Scripts\python.exe fly.py set --lat 25.0330 --lng 121.5654
```

Check status:

```powershell
.venv311\Scripts\python.exe fly.py status
```

Clear simulated location:

```powershell
.venv311\Scripts\python.exe fly.py clear
```

Run route (A -> B -> C -> A):

```powershell
.venv311\Scripts\python.exe fly.py route ^
  --from-lat 25.0330 --from-lng 121.5654 ^
  --via 25.0340,121.5660 ^
  --lat 25.0350 --lng 121.5670
```

### Web UI

Start UI:

```powershell
.venv311\Scripts\python.exe webui.py
```

Open:

```text
http://127.0.0.1:8765
```

Web UI supports:

- Search location
- Select/reorder up to 5 points
- `set` fixed point (Point A)
- `route` run closed loop route
- `clear` restore real GPS
- `status` / `doctor`
- Save/load/delete routes
- Route monitor panel

## CLI Commands

- `.venv311\Scripts\python.exe fly.py set --lat <lat> --lng <lng>`
- `.venv311\Scripts\python.exe fly.py route --from-lat <lat> --from-lng <lng> --lat <lat> --lng <lng> [--via lat,lng ...]`
- `.venv311\Scripts\python.exe fly.py clear`
- `.venv311\Scripts\python.exe fly.py status`
- `.venv311\Scripts\python.exe fly.py doctor`

## Troubleshooting (Windows)

### 1) `windows_admin: no`

Cause:

- Terminal not running as Administrator

Fix:

- Reopen PowerShell as Administrator

### 2) `This command requires admin privileges`

Cause:

- Tunnel command launched without elevated permissions

Fix:

- Run from Administrator PowerShell

### 3) `Device is not connected`

Cause:

- USB/trust/developer mode/session issues

Fix:

- Reconnect USB cable
- Unlock iPhone and tap Trust
- Confirm Developer Mode enabled
- Re-run `fly.py doctor`

### 4) `set` reports started but phone does not move

Check in order:

```powershell
.venv311\Scripts\python.exe fly.py status
Get-Content .fly_session.log
.venv311\Scripts\python.exe fly.py clear
```

Then start a fresh `set`.

### 5) Web UI search fails (502)

Cause:

- Geocoding upstream service unavailable / blocked

Fix:

- Retry later
- Use manual coordinates for set/route

## Local Runtime Files (Do Not Commit)

- `.fly_state.json`
- `.fly_session.log`
- `.fly_route.gpx`
- `.saved_routes.json`
- `__pycache__/`

`.gitignore` already excludes these files.

## Privacy & Security

- This is simulated location only.
- No permanent modification to iPhone hardware GPS.
- On Windows edition, macOS Keychain auth commands are not used.

## Third-Party Services

- Nominatim (OpenStreetMap) for geocoding
- OSRM public API for road routing

Availability/rate limits depend on public service status.

