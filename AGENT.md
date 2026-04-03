# AGENT.md

This workspace contains a Python utility for simulating iPhone GPS location with `pymobiledevice3`.
It also contains:

- a geocoding helper for address-to-coordinate lookup
- a small local Web UI for point selection and command execution

## Goal

- Target platform: iPhone on iOS 18 or newer
- Primary behavior: start simulated GPS at a specified latitude/longitude
- Secondary behavior: stop simulation and restore the iPhone's normal real location
- Route behavior: support explicit closed-loop routes such as `A -> B -> A` and `A -> B -> C -> D -> E -> A`
- Route point limit: at most 5 points total before returning to the first point
- Default route style: prefer realistic road-based routing when possible
- Web UI route config: support preset and manual modes.
- Preset route modes: `walk`, `cycle`, `car-direct`, and `car-road`.
- Helper behavior: convert world addresses into coordinates suitable for `fly.py`
- UI behavior: allow searching, selecting points, and triggering `set` / `route` / `clear` from a browser on localhost
- Session behavior: `set` and `route` should return control to the terminal and keep simulation in a background session

## Environment

- Run inside a Python virtual environment:
  - `source .venv/bin/activate`
- Expected dependency:
  - `pymobiledevice3`
- Geocoding dependency:
  - internet access to OpenStreetMap Nominatim
- Real-road routing dependency:
  - internet access to OSRM
- Current workspace entrypoints:
  - `python fly.py`
  - `python geocode.py`
  - `python webui.py`

## Implementation Rules

- Prefer `pymobiledevice3 developer dvt simulate-location` for iOS 18+.
- Keep the CLI explicit and stable.
- Support:
  - fixed-location `set`
  - explicit `clear`
  - route playback with up to 5 user-defined points
- Closed-loop route behavior should always return to the first waypoint.
- Prefer real-road routing when internet is available; fall back to straight-line interpolation only when routing is unavailable.
- For real-road routing, densify the returned path so GPX playback stays visually smoother and speed spikes are reduced.
- Prefer a user workflow where `set` or `route` starts in background and `clear` is the explicit stop action.
- Prefer resilient cleanup behavior: if a stored RSD is stale, `clear` should retry via a fresh tunnel.
- Prefer automatic tunnel creation over hard-coded long-lived RSD values.
- The Web UI should stay local-only by default.
- If password handling changes, document the security boundary clearly. Do not imply that stored sudo credentials are perfectly isolated from the current macOS user context.
- When behavior, CLI, setup steps, troubleshooting, or UI flows change, update `README.md` in the same change.
- Keep both `README.md` and `README.zh-TW.md` aligned when public-facing usage changes.
- Keep platform release guides `README.macos.en.md`, `README.macos.zh-TW.md`, `README.windows.en.md`, and `README.windows.zh-TW.md` aligned when platform setup or usage changes.
- Update `AGENT.md` too when project rules, assumptions, or maintenance workflow change.
- Do not claim the script changes the phone's permanent hardware GPS location.
- Favor actionable error messages for tunnel / developer mode / pairing / stale-RSD failures.

## Expected Usage

- Set location:
  - `python fly.py set --lat 25.0330 --lng 121.5654`
- Closed-loop route:
  - `python fly.py route --from-lat 25.0330 --from-lng 121.5654 --via 25.0340,121.5660 --lat 25.0350 --lng 121.5670`
- Clear location:
  - `python fly.py clear`
- Convert an address to coordinates:
  - `python geocode.py "Tokyo Tower, Japan"`
- Start local Web UI:
  - `python webui.py`
- Check local status:
  - `python fly.py status`
- Check troubleshooting tips:
  - `python fly.py doctor`
- Save sudo password to macOS Keychain:
  - `python fly.py auth-store`
- Check saved password status:
  - `python fly.py auth-status`
- Delete saved password:
  - `python fly.py auth-clear`

## Device Assumptions

- The iPhone is already trusted / paired.
- Developer Mode is enabled on the device.
- For iOS 18+, creating a tunnel generally requires root privileges.
- The default path is to auto-start a fresh tunnel with `sudo`.
- Disconnecting the iPhone from the Mac will usually break or destabilize simulated location.
