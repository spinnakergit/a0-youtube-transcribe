"""One-time setup script for the YouTube Transcriber plugin.
Installs required Python dependencies.

Called by the Init button in Agent Zero's Plugin List UI.
Must define main() returning 0 on success, non-zero on failure."""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("youtube_transcribe_init")


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
        logger.info("ffmpeg found.")
        return True
    logger.warning("ffmpeg not found. Frame extraction will be unavailable.")
    logger.warning("  Install with: apt-get install -y ffmpeg")
    return False


def main():
    python = _find_python()
    # Map of import name -> pip package name
    # youtube-transcript-api 1.0.0 (2025-02) replaced the static
    # YouTubeTranscriptApi.get_transcript() method with an instance .fetch().
    # The plugin supports both shapes, but the floor guarantees that any
    # fresh install ships with the documented 1.x surface.
    deps = {
        "yt_dlp": "yt-dlp",
        "youtube_transcript_api": "youtube-transcript-api>=1.0.0",
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
                logger.info(f"{pip_name} already installed.")
                continue
        except Exception:
            pass
        logger.info(f"Installing {pip_name}...")
        try:
            _install(pip_name, python)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install {pip_name}: {e}")
            failed.append(pip_name)

    _check_ffmpeg()

    if failed:
        logger.error(f"Failed to install: {', '.join(failed)}")
        return 1

    logger.info("All dependencies ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
