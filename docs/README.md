# YouTube Transcriber Plugin for Agent Zero

A YouTube transcription plugin for Agent Zero that extracts audio to text, detects visual references (charts, graphs, slides), and generates AI-powered summaries and detailed timestamped notes.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Tools Reference](#tools-reference)
- [Skills Reference](#skills-reference)
- [Usage Examples](#usage-examples)
- [Visual Context Pipeline](#visual-context-pipeline) (also see [VISUAL_CONTEXT.md](VISUAL_CONTEXT.md) for full reference)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- Agent Zero running on the **development branch** (plugin framework required)
- Python 3.10+ with `yt-dlp`, `youtube-transcript-api`, and `Pillow` (auto-installed)
- `ffmpeg` (for frame extraction -- usually pre-installed in Agent Zero containers)

### Step 1: Install the Plugin

Agent Zero runs inside a Docker container with a dual-path architecture:
- `/git/agent-zero/` -- source code (persists across rebuilds)
- `/a0/` -- runtime copy (where the server actually runs from)

You must install to **`/a0/`** for immediate effect. The install script handles this automatically.

**Method A -- Install script (recommended):**

```bash
# Copy plugin source into the container
docker cp a0-youtube-transcribe/ <container_name>:/tmp/a0-youtube-transcribe

# Run the installer
docker exec <container_name> bash /tmp/a0-youtube-transcribe/install.sh

# Restart Agent Zero
docker exec <container_name> supervisorctl restart run_ui
```

The install script:
- Auto-detects the Agent Zero root (`/a0/` or `/git/agent-zero/`)
- Copies plugin files to `usr/plugins/youtube_transcribe/`
- Creates the required symlink at `plugins/youtube_transcribe` -> `usr/plugins/youtube_transcribe`
- Installs Python dependencies (`yt-dlp`, `youtube-transcript-api`, `Pillow`)
- Copies skills to `usr/skills/`
- Enables the plugin (creates `.toggle-1`)
- Also copies to `/git/agent-zero/` for persistence across container rebuilds

**Method B -- Manual Docker install:**

```bash
# Copy plugin files
docker cp a0-youtube-transcribe/ <container_name>:/a0/usr/plugins/youtube_transcribe

# Create symlink (REQUIRED for Python imports)
docker exec <container_name> ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe

# Install dependencies
docker exec <container_name> /opt/venv-a0/bin/python /a0/usr/plugins/youtube_transcribe/initialize.py

# Copy skills
docker exec <container_name> bash -c 'cp -r /a0/usr/plugins/youtube_transcribe/skills/* /a0/usr/skills/'

# Enable the plugin
docker exec <container_name> touch /a0/usr/plugins/youtube_transcribe/.toggle-1

# Restart Agent Zero
docker exec <container_name> supervisorctl restart run_ui
```

> **Important:** The symlink from `plugins/youtube_transcribe` to `usr/plugins/youtube_transcribe` is **required**. Without it, Python imports like `from plugins.youtube_transcribe.helpers.youtube_client import ...` will fail with `ModuleNotFoundError`.

### Step 2: Verify Installation

Open the Agent Zero WebUI, navigate to the YouTube Transcriber plugin dashboard, and click **Check Status**. All four dependencies should show as available:

| Dependency | Purpose | Required |
|------------|---------|----------|
| `yt-dlp` | YouTube download and metadata | Yes |
| `youtube-transcript-api` | Caption/subtitle retrieval | Yes |
| `ffmpeg` | Video frame extraction | Optional (for visual context) |
| `Pillow` | Image handling | Optional (for visual context) |

Or test via CLI:

```bash
docker exec <container_name> curl -s -X POST http://localhost/api/plugins/youtube_transcribe/youtube_test | python3 -m json.tool
```

Expected output:
```json
{
    "status": "ok",
    "checks": {
        "yt_dlp": {"available": true, "version": "2026.03.03"},
        "youtube_transcript_api": {"available": true, "version": "installed"},
        "ffmpeg": {"available": true, "version": "ffmpeg version 8.0.1..."},
        "pillow": {"available": true, "version": "12.0.0"}
    },
    "message": "All dependencies available."
}
```

### Step 3: Start Using It

Open Agent Zero's chat and try:
> Transcribe this YouTube video: https://youtube.com/watch?v=VIDEO_ID

---

## Configuration

### Full Configuration Reference

Configuration is stored via Agent Zero's plugin settings system. Defaults come from `default_config.yaml`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `transcription.preferred_source` | string | `"captions"` | Transcript source: `captions` (YouTube subtitles) or `whisper` (local model) |
| `transcription.whisper_model` | string | `"base"` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `transcription.language` | string | `""` | ISO 639-1 language code (empty = auto-detect) |
| `visual.enabled` | bool | `true` | Enable visual context extraction |
| `visual.frame_interval` | int | `30` | Seconds between periodic frame samples |
| `visual.max_frames` | int | `20` | Maximum frames to extract per video |
| `visual.analyze_frames` | bool | `true` | Use LLM to analyze extracted frames |
| `output.save_to_memory` | bool | `true` | Auto-save to Agent Zero's memory |
| `output.export_format` | string | `"markdown"` | Export format: `markdown` or `text` |
| `output.include_timestamps` | bool | `true` | Include timestamps in transcripts |
| `playlist.max_videos` | int | `10` | Maximum videos to process per playlist |

### Configuring via WebUI

Navigate to the YouTube Transcriber plugin settings page in Agent Zero's WebUI to adjust settings. Use the embedded **"Save YouTube Transcriber Settings"** button (not the outer framework Save button).

---

## Tools Reference

The plugin provides 3 tools that Agent Zero's LLM can invoke:

### `youtube_transcribe`

Transcribe a YouTube video or playlist. Extracts text from YouTube captions (or auto-generated subtitles), detects references to visual content, and extracts/analyzes video frames.

| Argument | Required | Description |
|----------|----------|-------------|
| `url` | yes | YouTube video or playlist URL |
| `action` | no | `transcribe` (default) or `playlist` |
| `extract_visuals` | no | `true`/`false` -- extract and analyze frames (default: from config) |
| `language` | no | Language hint (ISO 639-1 code, e.g., `en`, `es`) |
| `save_to_memory` | no | `true`/`false` (default: `true`) |
| `max_videos` | no | Max videos from a playlist (default: 10) |

**Output:** Full transcript saved to file in `data/` directory. A preview (first 3,000 characters) is returned to the agent to avoid context window overflow.

**Supported URL formats:**
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- `https://www.youtube.com/playlist?list=PLAYLIST_ID`
- `https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID`

### `youtube_summary`

Generate a structured AI-powered summary from a video transcript. For long transcripts, automatically chunks the text, summarizes each chunk, and synthesizes a final summary.

| Argument | Required | Description |
|----------|----------|-------------|
| `url` | yes* | YouTube video URL (*one of url or transcript*) |
| `transcript` | yes* | Pre-extracted transcript text (*one of url or transcript*) |
| `language` | no | Language hint |
| `save_to_memory` | no | `true`/`false` (default: `true`) |

**Output format:**
- **Overview** -- 2-4 sentence high-level summary
- **Main Topics** -- numbered list with descriptions
- **Key Points** -- bulleted key arguments and claims
- **Data & Evidence** -- statistics and evidence cited
- **Conclusions & Takeaways** -- main recommendations

### `youtube_notes`

Generate detailed, timestamped study notes broken into time-based sections. Each section includes key points, visual content references, explanations, and notable quotes.

| Argument | Required | Description |
|----------|----------|-------------|
| `url` | yes* | YouTube video URL (*one of url or transcript*) |
| `transcript` | yes* | Pre-extracted transcript text (*one of url or transcript*) |
| `section_minutes` | no | Section length in minutes (default: 5) |
| `language` | no | Language hint |
| `save_to_memory` | no | `true`/`false` (default: `true`) |

**Section output format:**
- **Key Points** -- detailed points from this section
- **Visual Content Referenced** -- descriptions of charts/graphs/slides discussed
- **Details & Explanations** -- in-depth explanations and examples
- **Notable Quotes** -- key statements from the speaker

---

## Skills Reference

Two SKILL.md skills are included and installed to `usr/skills/`:

| Skill | Triggers | Description |
|-------|----------|-------------|
| `youtube-transcribe` | "transcribe youtube", "youtube transcript", "transcribe video" | Transcription workflow with visual context |
| `youtube-research` | "summarize youtube", "youtube notes", "analyze youtube" | Research workflow with summaries and notes |

Skills are loaded semantically -- just mention YouTube transcription or research in your message and Agent Zero will activate the appropriate skill.

---

## Usage Examples

### Example 1: Basic Transcription

**You say:**
> Transcribe this YouTube video: https://youtube.com/watch?v=abc123

**Agent Zero will:**
1. Call `youtube_transcribe` with the URL
2. Fetch video metadata (title, channel, duration)
3. Extract the transcript from YouTube captions
4. Save the full transcript to `data/transcript_abc123_Video_Title.md`
5. Save to memory (vector DB)
6. Return a preview of the first 3,000 characters

### Example 2: Summarize a Video

**You say:**
> Summarize this YouTube video: https://youtube.com/watch?v=abc123

**Agent Zero will:**
1. Call `youtube_summary` with the URL
2. Extract the transcript
3. If the transcript is long, chunk it and summarize each chunk
4. Synthesize a final structured summary
5. Save the summary to file and memory
6. Return: Overview, Main Topics, Key Points, Data & Evidence, Conclusions

### Example 3: Detailed Study Notes

**You say:**
> Create detailed notes from this video with 10-minute sections: https://youtube.com/watch?v=abc123

**Agent Zero will:**
1. Call `youtube_notes` with `section_minutes: 10`
2. Extract and group the transcript into 10-minute sections
3. Detect visual references in each section
4. Generate detailed notes for each section via LLM
5. Save full notes to file and memory
6. Return a preview with file path for full notes

### Example 4: Transcribe with Visual Analysis

**You say:**
> Transcribe this video and analyze any charts or graphs shown: https://youtube.com/watch?v=abc123

**Agent Zero will:**
1. Call `youtube_transcribe` with `extract_visuals: true`
2. Extract the transcript
3. Scan for visual keywords ("this chart", "as you can see", etc.)
4. Download the video and extract frames at those timestamps
5. Send each frame to the LLM for detailed visual analysis
6. Include visual context annotations in the output

### Example 5: Transcribe a Playlist

**You say:**
> Transcribe this playlist, max 5 videos: https://youtube.com/playlist?list=PLxxx

**Agent Zero will:**
1. Call `youtube_transcribe` with `action: playlist`, `max_videos: 5`
2. Resolve all video URLs in the playlist
3. Transcribe each video sequentially
4. Save individual transcript files + combined playlist file
5. Return a summary listing with file paths

### Example 6: Research Workflow (Multi-Step)

**You say:**
> I want to study this YouTube lecture. First transcribe it, then give me a summary, and finally create detailed 5-minute section notes.

**Agent Zero will run a multi-step workflow:**
1. `youtube_transcribe` -- extract full transcript, save to file
2. `youtube_summary` -- create structured summary from the transcript
3. `youtube_notes` -- create section-by-section study notes with visual context
4. Present the summary and note preview, with file paths to all outputs

### Example 7: Non-English Video

**You say:**
> Transcribe this Spanish YouTube video: https://youtube.com/watch?v=xyz789

**Agent Zero will:**
1. Call `youtube_transcribe` with `language: es`
2. Attempt Spanish captions first, then auto-generated Spanish subtitles
3. Transcript is returned in the original language

---

## Visual Context Pipeline

For full details, see [VISUAL_CONTEXT.md](VISUAL_CONTEXT.md).

### How It Works

1. **Keyword detection:** The transcript is scanned for 20+ visual keywords (e.g., "this chart", "as you can see", "look at this graph")
2. **Frame extraction:** For each detected reference, a video frame is extracted at that timestamp using ffmpeg
3. **LLM analysis:** Each frame is sent to the utility LLM with the speaker's words as context
4. **Annotation:** The LLM describes charts, graphs, tables, diagrams, and slides in detail
5. **Fallback:** If no visual references are detected, periodic frame sampling provides general visual context

### Visual Keywords Detected

The plugin scans for these phrases in the transcript:
- "as you can see", "look at this", "this chart", "this graph"
- "this slide", "this diagram", "on the screen", "shown here"
- "take a look", "if you look at", "the table shows", "this figure"
- "the data shows", "looking at the", "let me show you"
- And more (20+ patterns total)

---

## Architecture

### Plugin Structure

```
usr/plugins/youtube_transcribe/
+-- plugin.yaml              # Manifest (discovered by plugin framework)
+-- default_config.yaml      # Default settings
+-- initialize.py            # Dependency installer
+-- install.sh               # Automated installer
+-- helpers/
|   +-- __init__.py
|   +-- youtube_client.py    # URL parsing, metadata, transcripts, frames
+-- tools/
|   +-- youtube_transcribe.py  # Transcription + visual context
|   +-- youtube_summary.py     # AI summary generation (with chunking)
|   +-- youtube_notes.py       # Timestamped section notes
+-- prompts/
|   +-- agent.system.tool.youtube_transcribe.md
|   +-- agent.system.tool.youtube_summary.md
|   +-- agent.system.tool.youtube_notes.md
+-- api/
|   +-- youtube_test.py      # Dependency check endpoint
+-- webui/
|   +-- main.html            # Dashboard with status check + tool cards
|   +-- config.html          # Settings page
+-- skills/
|   +-- youtube-transcribe/SKILL.md
|   +-- youtube-research/SKILL.md
+-- data/                    # Runtime output (auto-created)
|   +-- transcript_<id>_<title>.md
|   +-- summary_<id>_<title>.md
|   +-- notes_<id>_<title>.md
|   +-- frames_<id>/         # Extracted video frames
```

### How It Works

1. **Plugin discovery:** Agent Zero scans `usr/plugins/` for directories containing `plugin.yaml`. A symlink at `plugins/youtube_transcribe` -> `usr/plugins/youtube_transcribe` enables Python imports.

2. **Tool invocation:** When you mention YouTube transcription, the LLM sees the tool prompts in its system context and outputs a tool call (e.g., `youtube_transcribe`). Agent Zero resolves the tool file, loads the class, and calls `execute()`.

3. **Transcript extraction:** The tool first tries `youtube-transcript-api` for fast caption retrieval. If unavailable, it falls back to `yt-dlp` subtitle download in json3 format.

4. **Visual analysis:** Frames are extracted via `ffmpeg` and sent to the LLM via `call_utility_model(attachments=[frame_path])` for multimodal analysis.

5. **Memory integration:** All tools use the memory plugin's API (`Memory.get(agent)` -> `db.insert_text()`) to persist results. If the memory plugin isn't available, results are saved as markdown files in `memory/youtube_transcripts/`, `memory/youtube_summaries/`, or `memory/youtube_notes/`.

6. **Context window management:** Full outputs are saved to files in `data/`. Only a truncated preview (3-6K chars) is returned in the tool response to prevent LLM context overflow.

### Data Flow

```
User Message ("Transcribe this video: URL")
    |
    v
Agent Zero LLM (sees tool prompts)
    |
    v
Tool Call: youtube_transcribe / youtube_summary / youtube_notes
    |
    v
youtube_client.py:
  - parse_youtube_url() -> video_id / playlist_id
  - get_video_info() -> metadata via yt-dlp
  - get_transcript() -> captions API / yt-dlp subtitles
  - detect_visual_references() -> keyword scan
  - extract_frames_at_timestamps() -> ffmpeg
    |
    v
(Optional) LLM analysis of frames via call_utility_model()
    |
    v
Full output -> saved to data/<file>.md
Full output -> saved to Agent Zero memory
Preview -> returned to LLM as Response
    |
    v
Agent responds to user with preview + file path
```

---

## Troubleshooting

### Plugin Not Loading

1. Verify `plugin.yaml` exists in the plugin directory
2. Check the symlink: `ls -la /a0/plugins/youtube_transcribe` -- should point to `/a0/usr/plugins/youtube_transcribe`
3. Check for `.toggle-1` file (or remove any `.toggle-0` file)
4. Make sure you're on the development branch (plugin framework required)
5. Check Agent Zero logs for loading errors

### "No module named 'plugins.youtube_transcribe'"

The symlink is missing. Create it:
```bash
docker exec <container_name> ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe
```

### "No transcript available"

- The video may not have captions or auto-generated subtitles
- Some creators disable captions on their videos
- Try specifying a language: `youtube_transcribe` with `language: en`
- Very new videos may not have auto-generated captions yet

### Token/Context Overflow (litellm.BadRequestError)

The full transcript exceeds the LLM's context window. The plugin now:
- Saves full output to `data/` files
- Returns only a preview (3,000 chars) to the agent
- `youtube_summary` automatically chunks long transcripts

If you still hit limits, the conversation may have accumulated too much context. Start a new conversation.

### "yt-dlp metadata failed"

- The video URL may be invalid or the video is private/deleted
- Try updating yt-dlp: `docker exec <container_name> uv pip install -U yt-dlp --python /opt/venv-a0/bin/python`
- Some videos are region-locked

### No Frames Extracted

- Ensure `ffmpeg` is installed: `docker exec <container_name> which ffmpeg`
- ffmpeg is usually pre-installed in Agent Zero containers
- Install manually if needed: `docker exec <container_name> apt-get install -y ffmpeg`

### Visual Analysis Not Working

- Your main chat model must support **vision/multimodal** input (e.g., GPT-4o, Claude Opus/Sonnet, Gemini Pro Vision)
- Text-only models cannot interpret video frames
- Check that `visual.enabled` and `visual.analyze_frames` are both `true` in config

### Memory Save Failures

If transcripts aren't saving to memory, the plugin falls back to writing markdown files:
- `memory/youtube_transcripts/transcript_YYYYMMDD_HHMMSS.md`
- `memory/youtube_summaries/summary_YYYYMMDD_HHMMSS.md`
- `memory/youtube_notes/notes_YYYYMMDD_HHMMSS.md`

Check that these directories exist and are writable.

### Config Changes Not Taking Effect

After editing config files directly, restart Agent Zero:
```bash
docker exec <container_name> supervisorctl restart run_ui
```

If updating Python code, also clear the bytecode cache:
```bash
docker exec <container_name> find /a0 -path '*/youtube_transcribe*/__pycache__' -type d -exec rm -rf {} +
docker exec <container_name> supervisorctl restart run_ui
```

### Files Changed But Not Taking Effect

Agent Zero runs from `/a0/`, not `/git/agent-zero/`. Always copy changes to `/a0/usr/plugins/youtube_transcribe/`, clear `__pycache__`, and restart:

```bash
docker cp your-file.py <container_name>:/a0/usr/plugins/youtube_transcribe/path/to/file.py
docker exec <container_name> find /a0 -path '*/youtube_transcribe*/__pycache__' -type d -exec rm -rf {} +
docker exec <container_name> supervisorctl restart run_ui
```
