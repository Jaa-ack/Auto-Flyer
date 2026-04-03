# Auto Fly for macOS

Auto Fly for macOS lets you run simulated iPhone GPS movement from a browser UI or CLI.

Download:

- Releases page: https://github.com/Jaa-ack/Auto-Flyer/releases
- Direct download:
  https://github.com/Jaa-ack/Auto-Flyer/releases/download/v0.1.0/auto-fly-macos-en-0.1.0.zip

## Install

```bash
git clone <your-repo-url>
cd Auto-Fly
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you downloaded a release zip, extract it first and run the commands inside that folder.

## Prepare iPhone

- connect by USB
- trust the Mac
- enable Developer Mode

## Start Web UI

```bash
source .venv/bin/activate
python webui.py
```

Open:

```text
http://127.0.0.1:8765
```

## Common Commands

Set point A:

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

Run route:

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --via 25.0340,121.5660 \
  --lat 25.0345 --lng 121.5670
```

Stop simulation:

```bash
python fly.py clear
```
