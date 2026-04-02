# Auto Fly

Auto Fly is a macOS project for simulated iPhone GPS movement.

Languages:

- English: `README.md`
- Traditional Chinese: `README.zh-TW.md`

Tools included:

- `webui.py`
  - browser UI
- `fly.py`
  - terminal CLI
- `geocode.py`
  - address-to-coordinate helper

## Author

Author: `jaaaaack`

## License

MIT License. See `LICENSE`.

## Install

1. Clone the repository.

```bash
git clone <your-repo-url>
cd Auto-Fly
```

2. Create a virtual environment.

```bash
python3 -m venv .venv
```

3. Activate it.

```bash
source .venv/bin/activate
```

4. Install dependencies.

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

5. Prepare the iPhone.

- connect the iPhone by USB
- trust the Mac
- enable Developer Mode

Developer Mode is usually here:

```text
Settings > Privacy & Security > Developer Mode
```

## Quick Start

### Browser UI

```bash
source .venv/bin/activate
python webui.py
```

Open:

```text
http://127.0.0.1:8765
```

### CLI

Search an address:

```bash
python geocode.py "Tokyo Tower, Tokyo, Japan"
```

Set a fixed point:

```bash
python fly.py set --lat 35.6584491 --lng 139.7455368
```

Clear simulated location:

```bash
python fly.py clear
```

## Web UI

Main flow:

1. search an address
2. add points
3. use `set` to set point `A`
4. use `route` to run `A -> B -> C ... -> A`
5. use `clear` to stop simulation

### Config Modes

- `preset`
- `manual`

### Preset Route Modes

- `walk`
- `cycle`
- `car-direct`
- `car-road`

### Route Timer

Shows:

- current state
- start time
- elapsed time
- end time

## Common CLI Commands

Set one point:

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

Negative coordinates are supported:

```bash
python fly.py set --lat 40.6860733 --lng -74.019077
```

Run a route:

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

## Build A Release Zip

Create a release package:

```bash
python build_release.py
```

It will generate:

```text
dist/auto-fly-<version>.zip
```

Current version is stored in:

```text
VERSION
```

## GitHub Release Suggestion

Recommended release flow:

1. update `VERSION`
2. run `python build_release.py`
3. create a GitHub Release
4. upload the generated zip from `dist/`

Release text files:

- English: `RELEASE_NOTES_v0.1.0.md`
- Traditional Chinese: `RELEASE_NOTES_v0.1.0.zh-TW.md`

GitHub repo description text:

- `GITHUB_DESCRIPTION.md`

## Local Files That Should Not Be Uploaded

These files stay local:

- `.fly_state.json`
- `.fly_session.log`
- `.fly_route.gpx`
- `.saved_routes.json`
- `__pycache__/`
- `.venv/`
- `dist/`

The repo already includes `.gitignore` for them.
