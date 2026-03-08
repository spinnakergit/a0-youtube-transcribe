# YouTube Transcriber Plugin for Agent Zero

A YouTube transcription plugin for Agent Zero that extracts audio to text, detects visual references (charts, graphs, slides), and generates AI-powered summaries and detailed timestamped notes.

## Features

- **Transcribe** single videos or entire playlists to text
- **Visual context extraction** -- detects when speakers reference charts, graphs, or slides and extracts/analyzes video frames
- **AI-powered summaries** with main topics, key points, data/evidence, and conclusions
- **Detailed timestamped notes** broken into sections with visual content annotations
- **Automatic memory storage** -- transcripts, summaries, and notes are saved to Agent Zero's memory system
- **Full file export** -- all outputs saved as markdown files for reference

## Quick Start

### 1. Install the Plugin

**Docker (recommended):**

```bash
# Copy plugin into the container
docker cp a0-youtube-transcribe/ <container_name>:/a0/usr/plugins/youtube_transcribe

# Create symlink for Python imports
docker exec <container_name> ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe

# Install Python dependencies
docker exec <container_name> /opt/venv-a0/bin/python /a0/usr/plugins/youtube_transcribe/initialize.py

# Copy skills
docker exec <container_name> bash -c 'cp -r /a0/usr/plugins/youtube_transcribe/skills/* /a0/usr/skills/'

# Enable the plugin
docker exec <container_name> touch /a0/usr/plugins/youtube_transcribe/.toggle-1

# Restart to load
docker exec <container_name> supervisorctl restart run_ui
```

**Using the install script (inside the container):**

```bash
# Copy the plugin source into the container first
docker cp a0-youtube-transcribe/ <container_name>:/tmp/a0-youtube-transcribe

# Run the installer
docker exec <container_name> bash /tmp/a0-youtube-transcribe/install.sh
```

The install script auto-detects the Agent Zero root (`/a0/` or `/git/agent-zero/`), copies files, creates the symlink, installs dependencies, and enables the plugin.

### 2. Verify Installation

Open Agent Zero's web interface, navigate to the YouTube Transcriber plugin dashboard, and click **Check Status**. All four dependencies should show as available:

- **yt-dlp** -- YouTube download and metadata
- **youtube-transcript-api** -- Caption retrieval
- **ffmpeg** -- Frame extraction
- **Pillow** -- Image handling

### 3. Start Using It

Open Agent Zero's chat and try:

| What you want | What to say |
|---------------|-------------|
| Transcribe a video | "Transcribe this YouTube video: https://youtube.com/watch?v=..." |
| Summarize a video | "Summarize this YouTube video: https://youtube.com/watch?v=..." |
| Detailed study notes | "Create detailed notes from this video: https://youtube.com/watch?v=..." |
| Transcribe a playlist | "Transcribe this playlist: https://youtube.com/playlist?list=..." |
| Transcribe with visuals | "Transcribe this video with visual analysis: https://youtube.com/watch?v=..." |

## Tools

| Tool | Description |
|------|-------------|
| `youtube_transcribe` | Transcribe a video or playlist with optional visual context extraction |
| `youtube_summary` | Generate an AI-powered structured summary from a video transcript |
| `youtube_notes` | Generate detailed, timestamped study notes broken into sections |

### youtube_transcribe

Extracts text from YouTube captions (or auto-generated subtitles), detects references to visual content, extracts video frames at those timestamps, and uses the LLM to describe charts, graphs, and slides.

**Arguments:**
- `url` (required) -- YouTube video or playlist URL
- `action` -- `transcribe` (default) or `playlist`
- `extract_visuals` -- `true`/`false` (default: from config)
- `language` -- Language hint (e.g., `en`, `es`)
- `save_to_memory` -- `true`/`false` (default: `true`)
- `max_videos` -- Max videos from a playlist (default: 10)

### youtube_summary

Generates a structured summary with overview, main topics, key points, data/evidence, and conclusions. Long transcripts are automatically chunked and synthesized.

**Arguments:**
- `url` -- YouTube video URL
- `transcript` -- Pre-extracted transcript text (alternative to url)
- `language` -- Language hint
- `save_to_memory` -- `true`/`false` (default: `true`)

### youtube_notes

Creates detailed study notes organized by time sections. Each section includes key points, visual content references, detailed explanations, and notable quotes.

**Arguments:**
- `url` -- YouTube video URL
- `transcript` -- Pre-extracted transcript text (alternative to url)
- `section_minutes` -- Section length in minutes (default: 5)
- `language` -- Language hint
- `save_to_memory` -- `true`/`false` (default: `true`)

## How It Works

### Transcript Pipeline
1. **YouTube captions** (via `youtube-transcript-api`) -- fastest, uses existing manual or auto-generated captions
2. **yt-dlp subtitle download** (fallback) -- downloads auto-generated subtitles in json3 format

### Visual Context Pipeline
1. Scans transcript for visual keywords ("this chart", "as you can see", "this slide", etc.)
2. Extracts video frames at detected timestamps using ffmpeg
3. Sends frames to the LLM for detailed visual analysis
4. If no explicit references found, periodic frame sampling provides general context

### Output Storage
- **Markdown files** -- Full transcripts, summaries, and notes saved to the plugin's `data/` directory
- **Agent Zero memory** -- Content indexed in the vector database for future retrieval
- **Response preview** -- Only a truncated preview is returned to the agent to avoid context window overflow

## Documentation

| Document | Description |
|----------|-------------|
| [docs/README.md](docs/README.md) | Full reference -- all tools, configuration, examples, architecture |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 5-minute setup guide |
| [docs/VISUAL_CONTEXT.md](docs/VISUAL_CONTEXT.md) | Visual context pipeline deep-dive |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | API endpoints and data formats |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | How to extend and contribute |

## Configuration

Settings can be adjusted via the WebUI config page or `default_config.yaml`:

| Section | Setting | Default | Description |
|---------|---------|---------|-------------|
| Transcription | `preferred_source` | `captions` | Caption source (`captions` or `whisper`) |
| Transcription | `language` | (auto) | ISO 639-1 language code |
| Visual | `enabled` | `true` | Enable visual context extraction |
| Visual | `frame_interval` | `30` | Seconds between periodic frame samples |
| Visual | `max_frames` | `20` | Max frames per video |
| Visual | `analyze_frames` | `true` | Use LLM to analyze extracted frames |
| Output | `save_to_memory` | `true` | Auto-save to Agent Zero memory |
| Output | `include_timestamps` | `true` | Include timestamps in transcripts |
| Playlist | `max_videos` | `10` | Max videos per playlist |

## Requirements

- Agent Zero (development branch with plugin framework)
- Python 3.10+
- System: `ffmpeg` (for frame extraction; usually pre-installed in Agent Zero containers)
- Python packages: `yt-dlp`, `youtube-transcript-api`, `Pillow` (auto-installed by `initialize.py`)

## Architecture

```
usr/plugins/youtube_transcribe/
├── plugin.yaml              # Plugin manifest
├── default_config.yaml      # Default settings
├── initialize.py            # Dependency installer
├── install.sh               # Automated installer
├── helpers/
│   └── youtube_client.py    # URL parsing, metadata, transcripts, frames
├── tools/
│   ├── youtube_transcribe.py  # Transcription + visual context
│   ├── youtube_summary.py     # AI summary generation
│   └── youtube_notes.py       # Timestamped study notes
├── prompts/                 # LLM tool descriptions
├── api/
│   └── youtube_test.py      # Dependency check endpoint
├── webui/
│   ├── main.html            # Dashboard with status + tool cards
│   └── config.html          # Settings page
├── skills/                  # 2 skill definitions
└── data/                    # Runtime output (transcripts, frames)
```

## Troubleshooting

- **"No transcript available"** -- The video may not have captions or auto-generated subtitles. Some videos have captions disabled by the creator.
- **Token/context overflow** -- If you hit LLM token limits, the plugin now saves full output to files and returns only a preview. Check the `data/` directory for complete transcripts.
- **No frames extracted** -- Ensure `ffmpeg` is installed: `which ffmpeg`. In Agent Zero containers it's usually pre-installed.
- **Plugin not loading** -- Ensure the symlink exists: `ls -la /a0/plugins/youtube_transcribe` should point to `/a0/usr/plugins/youtube_transcribe`
- **Import errors** -- The symlink at `/a0/plugins/youtube_transcribe` -> `/a0/usr/plugins/youtube_transcribe` is required for `from plugins.youtube_transcribe.helpers...` imports
