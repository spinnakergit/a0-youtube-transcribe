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
#       docker exec <container> ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Auto-detect A0 root: /a0 is the runtime copy, /git/agent-zero is the source
if [ -n "$1" ]; then
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

# Copy plugin files
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

# Create data directory
mkdir -p "$PLUGIN_DIR/data"

# Copy skills to usr/skills
SKILLS_DIR="$A0_ROOT/usr/skills"
echo "Copying skills..."
for skill_dir in "$SCRIPT_DIR/skills"/*/; do
    skill_name="$(basename "$skill_dir")"
    mkdir -p "$SKILLS_DIR/$skill_name"
    cp -r "$skill_dir"* "$SKILLS_DIR/$skill_name/"
done

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

# Create symlink so 'from plugins.youtube_transcribe.helpers...' imports work
SYMLINK="$A0_ROOT/plugins/youtube_transcribe"
if [ ! -e "$SYMLINK" ]; then
    ln -sf "$PLUGIN_DIR" "$SYMLINK"
    echo "Created symlink: $SYMLINK -> $PLUGIN_DIR"
fi

# If /a0 is a runtime copy of /git/agent-zero, also install there
if [ "$A0_ROOT" = "/a0" ] && [ -d "/git/agent-zero/usr" ]; then
    GIT_PLUGIN="/git/agent-zero/usr/plugins/youtube_transcribe"
    mkdir -p "$(dirname "$GIT_PLUGIN")"
    cp -r "$PLUGIN_DIR" "$GIT_PLUGIN" 2>/dev/null || true
fi

echo ""
echo "=== Installation complete ==="
echo "Plugin installed to: $PLUGIN_DIR"
echo "Skills installed to: $SKILLS_DIR"
echo ""
echo "Next steps:"
echo "  1. Restart Agent Zero to load the plugin"
echo "  2. Ask the agent: 'Transcribe this YouTube video: <url>'"
