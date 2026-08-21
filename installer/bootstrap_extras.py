#!/usr/bin/env python3
"""Shared installer helpers: stale package cleanup and Shaka Packager download."""

from __future__ import annotations

import argparse
import io
import platform
import shutil
import site
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def cleanup_stale_unplayplay_metadata() -> bool:
    """Remove broken unplayplay 0.0.8 dist-info that triggers repeated pip warnings."""
    removed: list[str] = []
    search_roots: list[Path] = []

    try:
        search_roots.extend(Path(p) for p in site.getsitepackages())
    except AttributeError:
        pass

    if site.ENABLE_USER_SITE:
        try:
            search_roots.append(Path(site.getusersitepackages()))
        except AttributeError:
            pass

    for root in search_roots:
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.name.startswith("unplayplay-0.0.8"):
                shutil.rmtree(entry, ignore_errors=True)
                removed.append(str(entry))

    if removed:
        print(f"[cleanup] Removed stale unplayplay metadata: {', '.join(removed)}")
    else:
        print("[cleanup] No stale unplayplay 0.0.8 metadata found")
    return bool(removed)


SHAKA_PACKAGER_ASSETS = {
    "Windows": ("packager-win-x64.exe", "packager-win-x64.exe"),
    "Darwin": ("packager-osx-x64", "packager-osx-x64"),
    "Linux": ("packager-linux-x64", "packager-linux-x64"),
}

# Bento4 mp4decrypt — DRM decryption fallback for when Shaka Packager is unusable
# (e.g. the bundled macOS Shaka build is too new for the host's libc++ and SIGABRTs).
# The macOS asset is a universal binary with a low deployment target, so it runs on
# older macOS (Big Sur) where Shaka Packager aborts. Zips contain bin/mp4decrypt[.exe].
_BENTO4_VERSION = "1-6-0-641"
_BENTO4_BASE_URL = "https://www.bok.net/Bento4/binaries"
MP4DECRYPT_ASSETS = {
    # platform: (local filename, bento4 zip name)
    "Windows": ("mp4decrypt.exe", f"Bento4-SDK-{_BENTO4_VERSION}.x86_64-microsoft-win32.zip"),
    "Darwin": ("mp4decrypt", f"Bento4-SDK-{_BENTO4_VERSION}.universal-apple-macosx.zip"),
    "Linux": ("mp4decrypt", f"Bento4-SDK-{_BENTO4_VERSION}.x86_64-unknown-linux.zip"),
}


def ensure_shaka_packager(project_root: Path | None = None) -> bool:
    """Download Shaka Packager (latest release) for the current OS if missing from project root."""
    root = project_root or PROJECT_ROOT
    asset = SHAKA_PACKAGER_ASSETS.get(platform.system())
    if not asset:
        print("[Shaka] Unknown platform; skipping Shaka Packager download")
        return False

    filename, url_name = asset
    dest = root / filename
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"[Shaka] Found {filename}")
        return True

    url = f"https://github.com/shaka-project/shaka-packager/releases/latest/download/{url_name}"
    print(f"[Shaka] Downloading {filename} from GitHub releases...")
    try:
        urllib.request.urlretrieve(url, dest)
        if platform.system() != "Windows":
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
        print(f"[Shaka] Saved to {dest}")
        return True
    except Exception as exc:
        print(f"[Shaka] WARNING: Could not download Shaka Packager: {exc}")
        return False


def ensure_mp4decrypt(project_root: Path | None = None) -> bool:
    """Download Bento4 mp4decrypt for the current OS if missing from project root.

    Extracts only the mp4decrypt binary from the official Bento4 SDK zip and drops
    it at the project root so resolve_mp4decrypt() can find it.
    """
    root = project_root or PROJECT_ROOT
    asset = MP4DECRYPT_ASSETS.get(platform.system())
    if not asset:
        print("[mp4decrypt] Unknown platform; skipping mp4decrypt download")
        return False

    filename, zip_name = asset
    dest = root / filename
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"[mp4decrypt] Found {filename}")
        return True

    url = f"{_BENTO4_BASE_URL}/{zip_name}"
    print(f"[mp4decrypt] Downloading Bento4 ({zip_name}) for mp4decrypt fallback...")
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            # bok.net rejects urllib's default User-Agent (HTTP 403), so present a browser-like one.
            request = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (OrpheusDL installer)"}
            )
            with urllib.request.urlopen(request) as response, open(tmp_path, "wb") as tmp_out:
                shutil.copyfileobj(response, tmp_out)
            with zipfile.ZipFile(tmp_path) as archive:
                member = _find_mp4decrypt_member(archive, filename)
                if member is None:
                    print(f"[mp4decrypt] WARNING: {filename} not found inside {zip_name}")
                    return False
                with archive.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if platform.system() != "Windows":
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
        print(f"[mp4decrypt] Saved to {dest}")
        return True
    except Exception as exc:
        print(f"[mp4decrypt] WARNING: Could not download mp4decrypt: {exc}")
        return False


def _find_mp4decrypt_member(archive: zipfile.ZipFile, filename: str):
    """Locate the mp4decrypt binary inside a Bento4 SDK zip (typically under bin/)."""
    target = filename.lower()
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        leaf = name.rsplit("/", 1)[-1].lower()
        if leaf == target:
            return info
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="OrpheusDL installer bootstrap helpers")
    parser.add_argument(
        "--shaka",
        action="store_true",
        help="Download Shaka Packager binary for the current platform",
    )
    parser.add_argument(
        "--mp4decrypt",
        action="store_true",
        help="Download Bento4 mp4decrypt binary (DRM decryption fallback)",
    )
    parser.add_argument(
        "--cleanup-unplayplay",
        action="store_true",
        help="Remove broken unplayplay 0.0.8 dist-info folders",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root directory (default: parent of installer/)",
    )
    args = parser.parse_args()

    if not args.cleanup_unplayplay and not args.shaka and not args.mp4decrypt:
        parser.error("Specify at least one of --cleanup-unplayplay, --shaka or --mp4decrypt")

    ok = True
    if args.cleanup_unplayplay:
        cleanup_stale_unplayplay_metadata()

    if args.shaka:
        ok = ensure_shaka_packager(args.project_root) and ok

    if args.mp4decrypt:
        # Fallback tool is best-effort; don't fail the whole install if it can't download.
        ensure_mp4decrypt(args.project_root)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
