"""Plugin lifecycle hooks for the YouTube Transcriber plugin.

Called by Agent Zero's plugin system during install, uninstall, and update.
See: helpers/plugins.py -> call_plugin_hook()
"""
import os
import subprocess
import sys
from pathlib import Path


def _get_plugin_dir() -> Path:
    """Return the directory this hooks.py lives in."""
    return Path(__file__).parent.resolve()


def _find_python() -> str:
    """Find the appropriate Python interpreter."""
    candidates = ["/opt/venv-a0/bin/python3", sys.executable, "python3"]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "python3"


def install(**kwargs):
    """Post-install hook: create data dir, install deps, enable plugin."""
    plugin_dir = _get_plugin_dir()
    plugin_name = "youtube_transcribe"

    print(f"[{plugin_name}] Running post-install hook...")

    # 1. Enable plugin
    toggle = plugin_dir / ".toggle-1"
    if not toggle.exists():
        toggle.touch()
        print(f"[{plugin_name}] Created {toggle}")

    # 2. Create data directory with restrictive permissions
    data_dir = plugin_dir / "data"
    data_dir.mkdir(exist_ok=True)
    os.chmod(str(data_dir), 0o700)

    # 3. Install Python dependencies via initialize.py
    init_script = plugin_dir / "initialize.py"
    if init_script.is_file():
        python = _find_python()
        try:
            subprocess.run(
                [python, str(init_script)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            print(f"[{plugin_name}] Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"[{plugin_name}] Warning: dependency install failed: {e.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"[{plugin_name}] Warning: dependency install timed out")

    print(f"[{plugin_name}] Post-install hook complete")


def uninstall(**kwargs):
    """Pre-uninstall hook."""
    plugin_name = "youtube_transcribe"
    print(f"[{plugin_name}] Running uninstall hook...")
    print(f"[{plugin_name}] Uninstall hook complete")
