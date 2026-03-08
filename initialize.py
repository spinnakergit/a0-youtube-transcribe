"""One-time setup script for the YouTube Transcriber plugin.
Installs required Python dependencies.

Called by the Init button in Agent Zero's Plugin List UI.
Must define main() returning 0 on success, non-zero on failure."""

import shutil
import subprocess
import sys
from pathlib import Path


def _find_python():
    """Find the correct Python interpreter (prefer A0 venv)."""
    venv_python = Path("/opt/venv-a0/bin/python")
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _install(pip_name: str, python: str):
    """Install a package using uv (preferred) or pip as fallback."""
    uv = shutil.which("uv")
    if uv:
        subprocess.check_call([uv, "pip", "install", pip_name, "--python", python])
    else:
        subprocess.check_call([python, "-m", "pip", "install", pip_name])


def _check_ffmpeg():
    """Check if ffmpeg is available (needed for frame extraction)."""
    if shutil.which("ffmpeg"):
        print("[YouTube Transcriber] ffmpeg found.")
        return True
    print("[YouTube Transcriber] WARNING: ffmpeg not found. Frame extraction will be unavailable.")
    print("  Install with: apt-get install -y ffmpeg")
    return False


def main():
    python = _find_python()
    # Map of import name -> pip package name
    deps = {
        "yt_dlp": "yt-dlp",
        "youtube_transcript_api": "youtube-transcript-api",
        "PIL": "Pillow",
    }
    failed = []
    for import_name, pip_name in deps.items():
        try:
            result = subprocess.run(
                [python, "-c", f"import {import_name}"],
                capture_output=True,
            )
            if result.returncode == 0:
                print(f"[YouTube Transcriber] {pip_name} already installed.")
                continue
        except Exception:
            pass
        print(f"[YouTube Transcriber] Installing {pip_name}...")
        try:
            _install(pip_name, python)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Failed to install {pip_name}: {e}")
            failed.append(pip_name)

    _check_ffmpeg()

    if failed:
        print(f"[YouTube Transcriber] Failed to install: {', '.join(failed)}")
        return 1

    print("[YouTube Transcriber] All dependencies ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
