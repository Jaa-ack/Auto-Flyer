# Auto Fly

Auto Fly is a cross-platform project for simulated iPhone GPS movement on macOS and Windows.

[Traditional Chinese](README.zh-TW.md)

## Download

Recommended download method: open GitHub Releases and choose the package for your system and language.

- Releases page: https://github.com/Jaa-ack/Auto-Flyer/releases
- Latest release: https://github.com/Jaa-ack/Auto-Flyer/releases/latest

Current packages:

- macOS English:
  https://github.com/Jaa-ack/Auto-Flyer/releases/download/v0.1.0/auto-fly-macos-en-0.1.0.zip
- macOS Traditional Chinese:
  https://github.com/Jaa-ack/Auto-Flyer/releases/download/v0.1.0/auto-fly-macos-zh-TW-0.1.0.zip
- Windows English:
  https://github.com/Jaa-ack/Auto-Flyer/releases/download/v0.1.0/auto-fly-windows-en-0.1.0.zip
- Windows Traditional Chinese:
  https://github.com/Jaa-ack/Auto-Flyer/releases/download/v0.1.0/auto-fly-windows-zh-TW-0.1.0.zip

Platform guides:

- [macOS English](README.macos.en.md)
- [macOS Traditional Chinese](README.macos.zh-TW.md)
- [Windows English](README.windows.en.md)
- [Windows Traditional Chinese](README.windows.zh-TW.md)

## What It Does

- Search an address and convert it to coordinates
- Set a fixed simulated GPS point on iPhone
- Run a closed-loop route such as `A -> B -> C -> A`
- Stop simulation and return to normal GPS
- Use the same Web UI flow on macOS and Windows

## Quick Start

1. Download the correct release zip from the links above.
2. Extract the zip file.
3. Create and activate a Python virtual environment.
4. Install dependencies with `requirements.txt`.
5. Connect the iPhone by USB, trust the computer, and enable Developer Mode.
6. Start `webui.py` or use `fly.py`.

For full steps, open the platform guide that matches your system and language.

## Release-First Usage

Most users should download from Releases instead of cloning the repository.

Use source clone only if you want to modify the project yourself.

## Development

If you want to work from source:

```bash
git clone https://github.com/Jaa-ack/Auto-Flyer.git
cd Auto-Fly
```

## Author

Author: `jaaaaack`

## License

MIT License. See `LICENSE`.
