"""Package the Luna extension into an uploadable zip for the Chrome Web Store.

Usage:  python scripts/package_extension.py
Output: dist/luna-extension-<version>.zip  (manifest.json at the zip root)
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
DIST = ROOT / "dist"

# Files/patterns that should NOT ship in the store package.
EXCLUDE_NAMES = {"README.md", ".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIXES = {".map", ".log"}


def should_include(path: Path) -> bool:
    if path.name in EXCLUDE_NAMES:
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return True


def main():
    manifest = json.loads((EXT / "manifest.json").read_text())
    version = manifest.get("version", "0.0.0")
    DIST.mkdir(exist_ok=True)
    out = DIST / f"luna-extension-{version}.zip"

    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(EXT.rglob("*")):
            if path.is_dir() or not should_include(path):
                continue
            zf.write(path, path.relative_to(EXT).as_posix())
            count += 1

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"Packaged {count} files -> {out}  ({size_mb:.1f} MB)")
    print("Upload this zip at https://chrome.google.com/webstore/devconsole")


if __name__ == "__main__":
    main()
