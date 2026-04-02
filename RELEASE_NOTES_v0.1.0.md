# Auto Fly v0.1.0

First public release of Auto Fly.

## Highlights

- Browser UI for search, point selection, `set`, `route`, and `clear`
- CLI tool for direct control
- Address-to-coordinate helper
- Preset route modes:
  - `walk`
  - `cycle`
  - `car-direct`
  - `car-road`
- Manual route configuration mode
- Saved routes in the Web UI
- Route timer with state, start time, elapsed time, and end time
- Release package builder via `python build_release.py`

## Included Files

- `webui.py`
- `fly.py`
- `geocode.py`
- `requirements.txt`
- `README.md`
- `README.zh-TW.md`

## Notes

- macOS only
- iPhone with iOS 18+ required
- Developer Mode must be enabled
- simulated location only; not permanent hardware GPS modification
