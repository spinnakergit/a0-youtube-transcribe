# Development Guide

How to extend, modify, and contribute to the YouTube Transcriber plugin.

---

## Plugin Framework Basics

This plugin follows Agent Zero's plugin framework conventions. Key rules:

- **`plugin.yaml`** in the root directory is required -- it's how the framework discovers the plugin
- **Tools** go in `tools/` -- one file per tool, one `Tool` subclass per file
- **Tool prompts** go in `prompts/agent.system.tool.<tool_name>.md` -- this is what the LLM reads
- **Helpers** go in `helpers/` -- imported as `from plugins.youtube_transcribe.helpers.<module> import ...`
- **API endpoints** go in `api/` -- auto-discovered Flask route handlers
- **WebUI** goes in `webui/` -- `main.html` (dashboard) and `config.html` (settings)
- **Config** is accessed via `plugins.get_plugin_config("youtube_transcribe", agent=self.agent)`

---

## Adding a New Tool

### Step 1: Create the tool file

Create `tools/youtube_chapters.py`:

```python
from helpers.tool import Tool, Response
from plugins.youtube_transcribe.helpers.youtube_client import (
    parse_youtube_url, get_video_info, get_transcript,
    format_transcript, get_yt_config,
)


class YouTubeChapters(Tool):
    """Extract and summarize video chapters."""

    async def execute(self, **kwargs) -> Response:
        url = self.args.get("url", "")
        if not url:
            return Response(message="Error: url is required.", break_loop=False)

        parsed = parse_youtube_url(url)
        video_id = parsed.get("video_id")
        if not video_id:
            return Response(message="Error: Invalid video URL.", break_loop=False)

        self.set_progress("Fetching video info...")
        try:
            info = get_video_info(url)
        except Exception as e:
            return Response(message=f"Error: {e}", break_loop=False)

        # Extract chapters from video description
        chapters = info.get("chapters", [])
        if not chapters:
            return Response(
                message="No chapters found in this video.",
                break_loop=False,
            )

        lines = [f"# Chapters: {info.get('title', 'Unknown')}"]
        for ch in chapters:
            start = ch.get("start_time", 0)
            title = ch.get("title", "Untitled")
            lines.append(f"- [{start//60:02d}:{start%60:02d}] {title}")

        return Response(message="\n".join(lines), break_loop=False)
```

### Step 2: Create the tool prompt

Create `prompts/agent.system.tool.youtube_chapters.md`:

```markdown
## youtube_chapters
Extract and list chapter markers from a YouTube video.

**Arguments:**
- **url** (string, required): YouTube video URL

~~~json
{"url": "https://www.youtube.com/watch?v=abc123"}
~~~
```

### Step 3: Restart Agent Zero

The plugin framework auto-discovers tools by filename. No registration needed.

---

## Extending the YouTube Client

### Adding a New Transcript Source

To add a new transcript source (e.g., Whisper), edit `helpers/youtube_client.py`:

```python
def get_transcript_whisper(video_url: str, model: str = "base") -> Optional[list[dict]]:
    """Transcribe audio using OpenAI Whisper."""
    import whisper

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download audio
        audio_path = os.path.join(tmpdir, "audio.mp3")
        subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--no-warnings", "--quiet",
            "-o", audio_path, video_url,
        ], check=True, timeout=300)

        # Transcribe
        model = whisper.load_model(model)
        result = model.transcribe(audio_path)

        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "text": seg["text"].strip(),
                "start": seg["start"],
                "duration": seg["end"] - seg["start"],
            })
        return segments
```

Then add it to the `get_transcript()` fallback chain:

```python
def get_transcript(video_id, video_url, language="", preferred="captions"):
    if preferred == "whisper":
        segments = get_transcript_whisper(video_url)
        if segments:
            return segments

    # Existing fallback chain...
    segments = get_transcript_captions(video_id, language)
    if segments:
        return segments

    segments = get_transcript_ytdlp(video_url, language)
    if segments:
        return segments

    raise RuntimeError("No transcript available")
```

### Adding New Visual Keywords

Edit the `VISUAL_KEYWORDS` list in `helpers/youtube_client.py`:

```python
VISUAL_KEYWORDS = [
    # Existing keywords...
    "as you can see",
    "this chart",
    # Add domain-specific keywords:
    "on the whiteboard",
    "this code snippet",
    "the architecture diagram",
    "in this screenshot",
]
```

---

## Adding an API Endpoint

Create `api/youtube_transcript_api.py`:

```python
from helpers.api import ApiHandler, Request, Response


class YouTubeTranscriptApi(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    async def process(self, input: dict, request: Request) -> dict | Response:
        url = input.get("url", "")
        if not url:
            return {"error": "url is required"}

        from plugins.youtube_transcribe.helpers.youtube_client import (
            parse_youtube_url, get_transcript, format_transcript,
        )

        parsed = parse_youtube_url(url)
        video_id = parsed.get("video_id")
        if not video_id:
            return {"error": "Invalid video URL"}

        try:
            segments = get_transcript(video_id, url)
            return {
                "ok": True,
                "video_id": video_id,
                "segments": len(segments),
                "transcript": format_transcript(segments)[:5000],
            }
        except Exception as e:
            return {"error": str(e)}
```

**Important API handler rules:**
- Must use `@classmethod` for `requires_csrf()` and `get_methods()`
- Use `async def process(self, input, request)` -- not `get()`/`post()`
- Return a dict (auto-serialized to JSON) or a Response object
- Set `requires_csrf()` to `False` for plugin APIs

---

## Testing Locally

Since the plugin depends on Agent Zero's framework (`helpers.tool`, `plugins.memory`, etc.), full testing requires a running Agent Zero instance.

**Quick validation -- test the client standalone:**

```python
import asyncio
from youtube_client import (
    parse_youtube_url, get_video_info, get_transcript,
    format_transcript, detect_visual_references,
)

url = "https://youtube.com/watch?v=abc123"
parsed = parse_youtube_url(url)
print(f"Type: {parsed['type']}, Video ID: {parsed['video_id']}")

info = get_video_info(url)
print(f"Title: {info['title']}, Duration: {info['duration']}s")

segments = get_transcript(parsed['video_id'], url)
print(f"Segments: {len(segments)}")
print(format_transcript(segments[:5]))

visual_refs = detect_visual_references(segments)
print(f"Visual references: {len(visual_refs)}")
for ref in visual_refs:
    print(f"  [{ref['timestamp']:.1f}s] {ref['keyword']}: {ref['text'][:80]}")
```

**Integration testing:**

1. Install the plugin into a running Agent Zero instance
2. Open the WebUI and verify dependencies via the dashboard
3. Ask the agent to transcribe a short video
4. Check `data/` directory for output files
5. Check Agent Zero logs for errors

---

## Known Limitations

### No Whisper Integration Yet

The `preferred_source: whisper` config option is defined but not yet implemented. The plugin currently only uses YouTube captions and yt-dlp subtitle download. See the "Adding a New Transcript Source" section above for implementation guidance.

### Context Window Management

Long transcripts can exceed LLM context limits. The plugin mitigates this by:
- Saving full output to files (not returning in Response)
- Returning only a preview (3-6K chars) to the agent
- Chunking long transcripts in `youtube_summary`
- Limiting section text to 8K chars in `youtube_notes`

However, accumulated conversation context can still cause overflow. Users should start a new conversation for very long videos.

### WebUI Config Uses Framework Store

The `webui/config.html` settings panel uses Agent Zero's framework settings store. As of March 2026, settings values are exposed on `config` (replacing the old `$store.pluginSettings.settings` pattern) and wrapper/modal variables on `context` (replacing `$store.pluginSettings`). The embedded save button is recommended for reliability.

---

## Project Structure Reference

```
a0-youtube-transcribe/
+-- README.md                # Top-level overview with quick start
+-- plugin.yaml              # Manifest -- do not rename
+-- default_config.yaml      # Defaults -- values used when no config exists
+-- initialize.py            # Run once to install deps (yt-dlp, youtube-transcript-api, Pillow)
+-- install.sh               # Automated installer (auto-detects /a0/ vs /git/agent-zero/)
+-- .gitignore
+-- LICENSE
+-- helpers/
|   +-- __init__.py
|   +-- youtube_client.py    # URL parsing, metadata, transcripts, frames, visual detection
+-- tools/
|   +-- youtube_transcribe.py  # Transcription + visual context + playlist
|   +-- youtube_summary.py     # AI summary (with chunking for long transcripts)
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
+-- data/                    # Runtime data (auto-created)
|   +-- transcript_*.md      # Full transcripts
|   +-- summary_*.md         # Full summaries
|   +-- notes_*.md           # Full notes
|   +-- frames_*/            # Extracted video frames
+-- docs/
    +-- README.md            # Full documentation (this file's parent)
    +-- QUICKSTART.md        # 5-minute setup guide
    +-- VISUAL_CONTEXT.md    # Visual context pipeline deep-dive
    +-- API_REFERENCE.md     # API endpoints and data formats
    +-- DEVELOPMENT.md       # This file
```

### Important: Plugin Installation Path

Agent Zero uses a dual-path architecture:
- `/git/agent-zero/` -- source code (persists across rebuilds)
- `/a0/` -- runtime copy (where the server runs from)

User plugins go in `usr/plugins/<name>/` but need a symlink at `plugins/<name>/` for Python imports:
```bash
ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe
```

Without this symlink, `from plugins.youtube_transcribe.helpers...` imports will fail with `ModuleNotFoundError`. The `install.sh` script creates this automatically.

When developing, always copy changes to `/a0/usr/plugins/youtube_transcribe/`, clear `__pycache__`, and restart:
```bash
docker cp your-file.py <container>:/a0/usr/plugins/youtube_transcribe/path/to/file.py
docker exec <container> find /a0 -path '*/youtube_transcribe*/__pycache__' -type d -exec rm -rf {} +
docker exec <container> supervisorctl restart run_ui
```
