import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
RELEASE_NAME = f"auto-fly-{VERSION}"
STAGING = DIST / RELEASE_NAME

INCLUDE_FILES = [
    "README.md",
    "README.zh-TW.md",
    "AGENT.md",
    "LICENSE",
    "GITHUB_DESCRIPTION.md",
    "RELEASE_NOTES_v0.1.0.md",
    "RELEASE_NOTES_v0.1.0.zh-TW.md",
    "fly.py",
    "geocode.py",
    "webui.py",
    "requirements.txt",
    ".gitignore",
    "VERSION",
]


def main():
    DIST.mkdir(exist_ok=True)
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir()

    for name in INCLUDE_FILES:
        source = ROOT / name
        target = STAGING / name
        shutil.copy2(source, target)

    archive_path = shutil.make_archive(str(DIST / RELEASE_NAME), "zip", DIST, RELEASE_NAME)
    print(f"Release package created: {archive_path}")


if __name__ == "__main__":
    main()
