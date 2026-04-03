# Auto Fly for Windows

Auto Fly for Windows lets you run simulated iPhone GPS movement from a browser UI or CLI.

## Install

```powershell
git clone <your-repo-url>
cd Auto-Fly
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Prepare iPhone

- connect by USB
- trust the PC
- enable Developer Mode
- open PowerShell or Terminal as Administrator when needed

## Start Web UI

```powershell
.venv\Scripts\python.exe webui.py
```

Open:

```text
http://127.0.0.1:8765
```

## Common Commands

Set point A:

```powershell
.venv\Scripts\python.exe fly.py set --lat 25.0330 --lng 121.5654
```

Run route:

```powershell
.venv\Scripts\python.exe fly.py route --from-lat 25.0330 --from-lng 121.5654 --via 25.0340,121.5660 --lat 25.0345 --lng 121.5670
```

Stop simulation:

```powershell
.venv\Scripts\python.exe fly.py clear
```
