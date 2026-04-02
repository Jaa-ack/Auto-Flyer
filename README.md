# iPhone GPS Simulation Helper

Open-source macOS utility for simulated iPhone GPS movement on iOS 18+ using `pymobiledevice3`.

This project provides:

- `webui.py`
  - local browser UI for search, point selection, `set`, `route`, and `clear`
- `fly.py`
  - terminal CLI for direct control and troubleshooting
- `geocode.py`
  - address-to-coordinate lookup helper

This project uses simulated location. It does not permanently modify the iPhone's hardware GPS.

## Author

Author: `jaaaaack`

## Before You Publish This Repo

These files are local runtime data and should not be committed:

- `.fly_state.json`
  - contains recent session state and timestamps
- `.fly_session.log`
  - may contain local paths, device session output, and troubleshooting logs
- `.fly_route.gpx`
  - contains your most recent route points
- `.saved_routes.json`
  - contains your personally saved routes and locations
- `__pycache__/`
  - local Python cache files

This repo now includes `.gitignore` so these files stay local by default.

## Requirements

- macOS
- Python 3.11+ recommended
- iPhone with iOS 18 or newer
- iPhone trusted / paired with the Mac
- Developer Mode enabled on the iPhone
- internet access for geocoding and real-road routing
- permission to use `sudo` when starting tunnels

## Setup On Any Mac

1. Clone the repository.

```bash
git clone <your-repo-url>
cd Moving
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

5. Connect your iPhone by USB and trust the Mac.

6. Enable Developer Mode on the iPhone.

Typical path:

```text
Settings > Privacy & Security > Developer Mode
```

If the option does not appear, first complete a developer pairing flow once with Xcode or another Apple developer workflow. Then restart the phone and enable Developer Mode.

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

Convert an address:

```bash
python geocode.py "Tokyo Tower, Tokyo, Japan"
```

Set a fixed location:

```bash
python fly.py set --lat 35.6584491 --lng 139.7455368
```

Clear simulated location:

```bash
python fly.py clear
```

## How The Project Works

- `set`
  - keeps the iPhone at one simulated point
- `route`
  - plays a closed loop such as `A -> B -> C -> A`
- `clear`
  - stops simulation and restores real GPS

Rules:

- `set` and `route` cannot run at the same time
- if a session is already running, use `python fly.py clear` first
- after `route` finishes, the phone stays at point `A`
- `clear` is the explicit way to return to real GPS
- if the iPhone disconnects from the Mac, simulated location usually stops or becomes unstable

## Web UI

Start it:

```bash
python webui.py
```

Change port if needed:

```bash
python webui.py --port 9000
```

### Main UI Sections

#### 1. Search

- `query`
  - address or place name
- `limit`
  - number of search results
- `搜尋`
  - search candidates

#### 2. Selected Points

- up to 5 points
- point `A` is always the start point
- `set` always uses point `A`
- each point supports:
  - `上移`
  - `下移`
  - `移除`
- `清空點位`
  - clear all selected points

#### 3. Saved Routes

- save current points with a custom route name
- load a saved route back into the editor
- start a saved route directly
- delete a saved route

Saved routes are stored locally in `.saved_routes.json`.

#### 4. Route Config

- `configMode`
  - `preset` or `manual`
- `routeMode`
  - `cycle`, `walk`, `car-direct`, `car-road`
- `speedKph`
- `stepMeters`
- `routeSource`
- `pauseSeconds`
- `routeProfile`

In `preset` mode, the fields are auto-filled.

In `manual` mode, you can edit them yourself.

#### 5. Action Buttons

- `set 到 A 點`
  - set point `A` as the simulated location
- `route 閉環移動`
  - run `A -> B -> C ... -> A`
- `clear`
  - stop simulation
- `status`
  - show current status

#### 6. Route Timer

Shows:

- current route state
- start time
- elapsed time
- end time

It does not show remaining time or countdown reminders.

### Preset Modes

- `cycle`
  - `cycling`, `16 km/h`, `osrm`, dense route points
- `walk`
  - `foot`, `4.8 km/h`, `osrm`, dense route points
- `car-direct`
  - `driving`, `100 km/h`, `linear`
  - fast straight-line travel to the target
- `car-road`
  - `driving`, `80 km/h`, `osrm`
  - faster road-based car travel

### Route Return Behavior

For multi-point routes such as `A -> B -> C`, the final leg is generated as:

```text
C -> A
```

That means:

- with `osrm`, the app generates a best route from the last point back to `A`
- with `linear`, it draws a direct line from the last point back to `A`

It is not a simple reverse playback of the original path unless that happens naturally.

## CLI Usage

### Set A Fixed Point

```bash
python fly.py set --lat 25.0330 --lng 121.5654
```

Negative coordinates are supported:

```bash
python fly.py set --lat 40.6860733 --lng -74.019077
```

### Run A Route

Two points:

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --lat 25.0345 --lng 121.5670
```

Three points:

```bash
python fly.py route \
  --from-lat 25.0330 --from-lng 121.5654 \
  --via 25.0340,121.5660 \
  --lat 25.0345 --lng 121.5670
```

Up to five points:

```text
A -> B -> C -> D -> E -> A
```

### Status

```bash
python fly.py status
```

### Doctor

```bash
python fly.py doctor
```

### Clear

```bash
python fly.py clear
```

## Geocoding

Basic usage:

```bash
python geocode.py "Tokyo Tower, Tokyo, Japan"
```

Recommended formats:

- landmark, city, country
- street number, street, district, city, postal code, country
- English or romaji for Japanese addresses when possible

Examples:

```bash
python geocode.py "Eiffel Tower, Paris, France"
python geocode.py "2 Chome-27-2 Hashimoto, Nishi Ward, Fukuoka, 819-0031, Japan"
```

The tool also tries to normalize:

- Google Maps URLs
- line breaks
- full-width characters
- `〒`
- postal code + country name stuck together
- some Chinese / Japanese country names

## Privacy And Security Notes

- this project can store a sudo password in macOS Keychain if you use:
  - `python fly.py auth-store`
- this is better than saving the password in plain text
- it is still tied to your macOS user context
- for stricter control, use a more limited `sudoers` rule instead

## Third-Party Services

This project currently uses public services:

- OpenStreetMap Nominatim for geocoding
- OSRM public routing for real-road paths

That means:

- normal low-volume personal use usually does not create a direct bill
- service availability and rate limits depend on the public service
- if you later replace them with commercial APIs, charges may apply

References:

- Nominatim Usage Policy: https://operations.osmfoundation.org/policies/nominatim/
- OSRM API Docs: https://project-osrm.org/docs/v5.24.0/api/

## Troubleshooting

### Route Timing Looks Wrong

The route timer now tracks:

- state
- start timestamp
- elapsed time
- end timestamp

It does not rely on a remaining-time countdown anymore.

### Developer Mode Missing

If `Developer Mode` is not visible on the phone:

- connect the iPhone to the Mac
- trust the Mac
- complete a developer pairing flow once
- restart the iPhone
- check:

```text
Settings > Privacy & Security > Developer Mode
```

### Device Disconnects

If the iPhone disconnects from the Mac, tunnel-based simulation usually stops.

## Files

- `webui.py`
- `fly.py`
- `geocode.py`
- `requirements.txt`
- `.gitignore`
- `README.md`
- `AGENT.md`
