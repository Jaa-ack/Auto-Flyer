# AGENT.md

Windows-first implementation guide for `Auto-Flyer`.

## Product Direction

This project originally targeted macOS. The active direction is now:

- Primary target: **Windows 10/11 + iPhone (iOS 18+)**
- Core capability:
  - set a fixed simulated location
  - run route playback (`A -> B -> ... -> A`)
  - clear and restore real GPS
- Interface priority:
  - Phase 1: `fly.py` CLI only
  - Phase 2: `webui.py` on Windows

This tool uses simulated location and does not permanently modify hardware GPS.

## Current Ground Truth

- `pymobiledevice3` works on Windows with Python 3.11.
- Tunnel startup on Windows requires **Administrator** privileges.
- macOS-only features must remain gated:
  - Keychain password commands (`auth-store`, `auth-status`, `auth-clear`)
  - AppleScript notifications (`osascript`)

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

- Python 3.11 virtual environment
- USB-connected iPhone trusted by the PC
- iPhone Developer Mode enabled
- PowerShell launched as Administrator for tunnel-related commands

## Engineering Rules

- Prefer explicit, actionable errors over generic failures.
- Never run macOS-only commands on Windows code paths.
- Keep `fly.py` behavior stable:
  - `set`/`route` run in background session
  - `clear` is explicit stop action
- Preserve compatibility with existing macOS behavior unless a fix is required.
- When CLI behavior changes, update `README.md` in the same change.

## Milestones

### M1: Windows CLI Reliability (in progress)

Goals:
- `fly.py doctor` reports Windows readiness (including admin state).
- `fly.py set` on non-admin shell fails fast with clear remediation.
- `fly.py set` on admin shell can start tunnel and attempt location set.
- `fly.py clear` and process cleanup work on Windows process model.

Acceptance checks:
- `.venv311\Scripts\python.exe fly.py doctor`
- `.venv311\Scripts\python.exe fly.py set --lat 25.0330 --lng 121.5654`
- `.venv311\Scripts\python.exe fly.py status`
- `.venv311\Scripts\python.exe fly.py clear`

### M2: Route Stability on Windows

Goals:
- Route generation and playback are stable with 2-5 waypoints.
- Session and tunnel lifecycle cleanup remains reliable after route completion/failure.

Acceptance checks:
- `.venv311\Scripts\python.exe fly.py route --from-lat ... --from-lng ... --lat ... --lng ...`
- `.venv311\Scripts\python.exe fly.py status`
- `.venv311\Scripts\python.exe fly.py clear`

### M3: Web UI on Windows

Goals:
- `webui.py` can drive Windows `fly.py` flows.
- UI surfaces common Windows failures with actionable hints.

Acceptance checks:
- `.venv311\Scripts\python.exe webui.py`
- Browser flow: search -> set -> status -> clear

## Debugging Playbook (Windows)

1. Verify admin state:
   - `.venv311\Scripts\python.exe fly.py doctor`
   - expect `windows_admin: yes`
2. Verify device is connected:
   - if `start-tunnel` reports device not connected, re-check USB cable, trust prompt, and Developer Mode.
3. Verify session state:
   - `.venv311\Scripts\python.exe fly.py status`
4. Recover:
   - `.venv311\Scripts\python.exe fly.py clear`

## Near-term TODO

- Improve `doctor` output with explicit "ready/not-ready" summary.
- Add Windows-specific troubleshooting section in README for:
  - admin shell
  - trust flow
  - Developer Mode visibility
  - tunnel permission errors
- Add one-command smoke-test helper for Windows CLI path.
