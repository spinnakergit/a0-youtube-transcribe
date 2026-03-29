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


def _get_a0_root() -> Path:
    """Detect A0 root directory."""
    if Path("/a0/plugins").is_dir():
        return Path("/a0")
    if Path("/git/agent-zero/plugins").is_dir():
        return Path("/git/agent-zero")
    return Path("/a0")


def _find_python() -> str:
    """Find the appropriate Python interpreter."""
    candidates = ["/opt/venv-a0/bin/python3", sys.executable, "python3"]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "python3"


def install(**kwargs):
    """Post-install hook: set up data dir, deps, skills, toggle."""
    plugin_dir = _get_plugin_dir()
    a0_root = _get_a0_root()
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

    # 3. Install skills
    skills_src = plugin_dir / "skills"
    skills_dst = a0_root / "usr" / "skills"
    if skills_src.is_dir():
        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir():
                target = skills_dst / skill_dir.name
                target.mkdir(parents=True, exist_ok=True)
                for f in skill_dir.iterdir():
                    dest = target / f.name
                    if f.is_file():
                        dest.write_bytes(f.read_bytes())
                print(f"[{plugin_name}] Installed skill: {skill_dir.name}")

    # 4. Install Python dependencies via initialize.py
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

    # 5. Mirror to /git/agent-zero if running in /a0 runtime
    if str(a0_root) == "/a0" and Path("/git/agent-zero/usr").is_dir():
        git_plugin = Path("/git/agent-zero/usr/plugins") / plugin_name
        if not git_plugin.exists():
            try:
                import shutil
                shutil.copytree(str(plugin_dir), str(git_plugin))
            except Exception:
                pass

    print(f"[{plugin_name}] Post-install hook complete")


def uninstall(**kwargs):
    """Pre-uninstall hook: clean up skills."""
    a0_root = _get_a0_root()
    plugin_name = "youtube_transcribe"

    print(f"[{plugin_name}] Running uninstall hook...")


    # Remove skills
    skills_dst = a0_root / "usr" / "skills"
    for skill_name in ['youtube-research', 'youtube-transcribe']:
        skill_path = skills_dst / skill_name
        if skill_path.is_dir():
            import shutil
            shutil.rmtree(str(skill_path))
            print(f"[{plugin_name}] Removed skill: {skill_name}")

    print(f"[{plugin_name}] Uninstall hook complete")
