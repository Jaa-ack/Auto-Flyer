import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
RELEASE_NOTES_EN = f"RELEASE_NOTES_v{VERSION}.md"
RELEASE_NOTES_ZH = f"RELEASE_NOTES_v{VERSION}.zh-TW.md"

COMMON_FILES = [
    "AGENT.md",
    "LICENSE",
    "GITHUB_DESCRIPTION.md",
    RELEASE_NOTES_EN,
    RELEASE_NOTES_ZH,
    "README.md",
    "README.zh-TW.md",
    "fly.py",
    "geocode.py",
    "webui.py",
    "requirements.txt",
    ".gitignore",
    "VERSION",
]

VARIANTS = [
    {
        "name": f"auto-fly-macos-en-{VERSION}",
        "readme_source": "README.macos.en.md",
    },
    {
        "name": f"auto-fly-macos-zh-TW-{VERSION}",
        "readme_source": "README.macos.zh-TW.md",
    },
    {
        "name": f"auto-fly-windows-en-{VERSION}",
        "readme_source": "README.windows.en.md",
    },
    {
        "name": f"auto-fly-windows-zh-TW-{VERSION}",
        "readme_source": "README.windows.zh-TW.md",
    },
]


def build_variant(variant):
    release_name = variant["name"]
    staging = DIST / release_name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for name in COMMON_FILES:
        shutil.copy2(ROOT / name, staging / name)

    shutil.copy2(ROOT / variant["readme_source"], staging / "README.release.md")
    shutil.copy2(ROOT / variant["readme_source"], staging / "README.md")

    archive_path = shutil.make_archive(str(DIST / release_name), "zip", DIST, release_name)
    return archive_path


def main():
    DIST.mkdir(exist_ok=True)
    created = []
    for variant in VARIANTS:
        created.append(build_variant(variant))

    print("Release packages created:")
    for path in created:
        print(path)


if __name__ == "__main__":
    main()
