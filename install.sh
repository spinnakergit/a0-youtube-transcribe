#!/bin/bash
# Install the YouTube Transcriber plugin into an Agent Zero instance.
#
# Usage:
#   ./install.sh                          # Auto-detect Agent Zero root (/a0 or /git/agent-zero)
#   ./install.sh /path/to/agent-zero      # Install to specified path
#
# For Docker:
#   docker exec <container> bash -c "cd /tmp && ./install.sh"
#   Or: docker cp a0-youtube-transcribe/ <container>:/a0/usr/plugins/youtube_transcribe && \

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Auto-detect A0 root: /a0 is the runtime copy, /git/agent-zero is the source
if [ -n "${1:-}" ]; then
    A0_ROOT="$1"
elif [ -d "/a0/plugins" ]; then
    A0_ROOT="/a0"
elif [ -d "/git/agent-zero/plugins" ]; then
    A0_ROOT="/git/agent-zero"
else
    echo "Error: Cannot find Agent Zero. Pass the path as argument."
    exit 1
fi

PLUGIN_DIR="$A0_ROOT/usr/plugins/youtube_transcribe"

echo "=== YouTube Transcriber Plugin Installer ==="
echo "Source:  $SCRIPT_DIR"
echo "Target:  $PLUGIN_DIR"
echo ""

# Create target directory
mkdir -p "$PLUGIN_DIR"

# Copy plugin files (skip if already installed in-place, e.g. via A0 plugin installer)
if [ "$(realpath "$SCRIPT_DIR")" != "$(realpath "$PLUGIN_DIR")" ]; then
    echo "Copying plugin files..."
    cp -r "$SCRIPT_DIR/plugin.yaml" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/default_config.yaml" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/initialize.py" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/helpers" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/tools" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/prompts" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/api" "$PLUGIN_DIR/"
    cp -r "$SCRIPT_DIR/webui" "$PLUGIN_DIR/"

    # Copy README and LICENSE if present
    [ -f "$SCRIPT_DIR/README.md" ] && cp "$SCRIPT_DIR/README.md" "$PLUGIN_DIR/"
    [ -f "$SCRIPT_DIR/LICENSE" ] && cp "$SCRIPT_DIR/LICENSE" "$PLUGIN_DIR/"
else
    echo "Files already in place (installed via plugin manager), skipping copy..."
fi

# Create data directory
mkdir -p "$PLUGIN_DIR/data"

# Install system dependencies (ffmpeg)
if ! command -v ffmpeg &>/dev/null; then
    echo "Installing ffmpeg..."
    apt-get update -qq && apt-get install -y -qq ffmpeg 2>/dev/null || \
        echo "WARNING: Could not install ffmpeg. Frame extraction will be unavailable."
fi

# Run initialization (install Python deps)
echo "Installing Python dependencies..."
python3 "$PLUGIN_DIR/initialize.py" 2>/dev/null || python "$PLUGIN_DIR/initialize.py"

# Enable plugin
touch "$PLUGIN_DIR/.toggle-1"

echo ""
echo "=== Installation complete ==="
echo "Plugin installed to: $PLUGIN_DIR"
echo ""
echo "Next steps:"
echo "  1. Restart Agent Zero to load the plugin"
echo "  2. Ask the agent: 'Transcribe this YouTube video: <url>'"
