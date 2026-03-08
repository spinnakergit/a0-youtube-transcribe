# Quick Start Guide

Get the YouTube Transcriber plugin running in under 5 minutes.

---

## 1. Install the Plugin (1 min)

```bash
# Copy plugin into the container
docker cp a0-youtube-transcribe/ <container_name>:/tmp/a0-youtube-transcribe

# Run the automated installer
docker exec <container_name> bash /tmp/a0-youtube-transcribe/install.sh

# Restart Agent Zero
docker exec <container_name> supervisorctl restart run_ui
```

The installer handles everything: copying files, creating the required symlink, installing dependencies, copying skills, and enabling the plugin.

**Alternative -- manual install:**

```bash
docker cp a0-youtube-transcribe/ <container_name>:/a0/usr/plugins/youtube_transcribe
docker exec <container_name> ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe
docker exec <container_name> /opt/venv-a0/bin/python /a0/usr/plugins/youtube_transcribe/initialize.py
docker exec <container_name> bash -c 'cp -r /a0/usr/plugins/youtube_transcribe/skills/* /a0/usr/skills/'
docker exec <container_name> touch /a0/usr/plugins/youtube_transcribe/.toggle-1
docker exec <container_name> supervisorctl restart run_ui
```

## 2. Verify It Works (30 sec)

**Option A -- WebUI:**

Open the Agent Zero web interface, go to the YouTube Transcriber plugin dashboard, and click **Check Status**. You should see green indicators for yt-dlp, youtube-transcript-api, ffmpeg, and Pillow.

**Option B -- CLI:**

```bash
docker exec <container_name> curl -s -X POST http://localhost/api/plugins/youtube_transcribe/youtube_test | python3 -m json.tool
```

You should see `"status": "ok"` with all checks passing.

## 3. Start Using It

Open Agent Zero's chat and try these:

### Transcribe a video
> Transcribe this YouTube video: https://youtube.com/watch?v=VIDEO_ID

### Summarize a video
> Summarize this YouTube video: https://youtube.com/watch?v=VIDEO_ID

### Create study notes
> Create detailed notes from this video: https://youtube.com/watch?v=VIDEO_ID

### Transcribe with visual analysis
> Transcribe this video and analyze any charts shown: https://youtube.com/watch?v=VIDEO_ID

### Transcribe a playlist
> Transcribe this playlist: https://youtube.com/playlist?list=PLAYLIST_ID

### Specify language
> Transcribe this Spanish video: https://youtube.com/watch?v=VIDEO_ID

---

## What Happens Next

- **Transcripts** are saved to `data/transcript_<id>_<title>.md` inside the plugin directory
- **Summaries** are saved to `data/summary_<id>_<title>.md`
- **Notes** are saved to `data/notes_<id>_<title>.md`
- All outputs are also indexed in **Agent Zero's memory** (vector DB) for future retrieval
- Only a **preview** is returned to the agent chat to avoid context window overflow
- You can reference past transcripts in future conversations -- Agent Zero remembers

## Common Patterns

| What you want | What to say |
|---------------|-------------|
| Quick transcript | "Transcribe this video: [url]" |
| Quick summary | "Summarize this video: [url]" |
| Study material | "Create detailed 5-minute section notes from: [url]" |
| Visual analysis | "Transcribe with visual analysis: [url]" |
| Batch processing | "Transcribe this playlist (max 5 videos): [url]" |
| Research workflow | "Transcribe, then summarize, then create notes from: [url]" |
| Different language | "Transcribe this French video: [url]" |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Plugin not loading | Check symlink: `ls -la /a0/plugins/youtube_transcribe` should point to `/a0/usr/plugins/youtube_transcribe` |
| "No module named 'plugins.youtube_transcribe'" | Create symlink: `ln -sf /a0/usr/plugins/youtube_transcribe /a0/plugins/youtube_transcribe` |
| API returns 404 | Files must be in `/a0/` (not just `/git/agent-zero/`). Re-run the installer or copy manually |
| "No transcript available" | Video may not have captions. Try specifying `language: en` |
| Token/context overflow | Start a new conversation -- accumulated context may be too large |
| No frames extracted | Ensure ffmpeg is installed: `which ffmpeg` |
| Changes not taking effect | Clear cache: `find /a0 -path '*/youtube_transcribe*/__pycache__' -exec rm -rf {} +` then `supervisorctl restart run_ui` |

For detailed troubleshooting, see [README.md](README.md#troubleshooting).
