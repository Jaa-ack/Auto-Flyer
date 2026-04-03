# Auto Fly

Auto Fly is a cross-platform project for simulated iPhone GPS movement on macOS and Windows, with the same Web UI and CLI workflow on both systems.

Languages:

- English: `README.md`
- Traditional Chinese: `README.zh-TW.md`

## Download Variants

Release packages are prepared in four variants:

- macOS English
- macOS Traditional Chinese
- Windows English
- Windows Traditional Chinese

Platform-specific quick guides:

- macOS English: `README.macos.en.md`
- macOS Traditional Chinese: `README.macos.zh-TW.md`
- Windows English: `README.windows.en.md`
- Windows Traditional Chinese: `README.windows.zh-TW.md`

## Included Tools

- `webui.py`
  - local browser UI
- `fly.py`
  - command line tool
- `geocode.py`
  - address to coordinate helper

## Quick Start

1. Clone the repository.

```powershell
git clone <your-repo-url>
cd Auto-Fly
```

2. Create and activate a virtual environment.

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

3. Install dependencies.

```powershell
cd "C:\path\to\Auto-Flyer"
.venv311\Scripts\python.exe fly.py doctor
```

4. Prepare the iPhone.

- connect the iPhone by USB
- trust the computer
- enable Developer Mode
- on Windows, open PowerShell or Terminal as Administrator when needed

5. Start the Web UI.

macOS:

```bash
python webui.py
```

Windows:

```powershell
.venv\Scripts\python.exe webui.py
```

Open:

```text
http://127.0.0.1:8765
```

## Daily Use

Main flow:

1. search an address
2. add points
3. use `set` to set point `A`
4. use `route` to run `A -> B -> C ... -> A`
5. use `clear` to stop simulation

Preset route modes:

- `walk`
- `cycle`
- `car-direct`
- `car-road`

The route timer shows:

- current state
- start time
- elapsed time
- end time

## Common CLI Commands

Search an address:

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

Set point `A`:

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

Run a closed-loop route:

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --via 25.0340,121.5660 \
  --lat 25.0345 --lng 121.5670
```

Check status:

```bash
python fly.py status
```

Stop simulation:

```bash
python fly.py clear
```

Negative coordinates are supported:

```bash
python fly.py set --lat 40.6860733 --lng -74.019077
```

## Build Release Packages

Create all four release zip files:

```bash
python build_release.py
```

Generated files:

```text
dist/auto-fly-macos-en-<version>.zip
dist/auto-fly-macos-zh-TW-<version>.zip
dist/auto-fly-windows-en-<version>.zip
dist/auto-fly-windows-zh-TW-<version>.zip
```

Current version is stored in `VERSION`.

## Release Files

- GitHub description: `GITHUB_DESCRIPTION.md`
- English release notes: `RELEASE_NOTES_v<version>.md`
- Traditional Chinese release notes: `RELEASE_NOTES_v<version>.zh-TW.md`

## Author

Author: `jaaaaack`

## License

MIT License. See `LICENSE`.

## Local Files That Should Not Be Uploaded

These files stay local:

- `.fly_state.json`
- `.fly_session.log`
- `.fly_route.gpx`
- `.saved_routes.json`
- `__pycache__/`
- `.venv/`
- `dist/`
- `backups/`

The repo already includes `.gitignore` for them.
