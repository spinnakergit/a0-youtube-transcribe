# API Reference

Internal REST API endpoints and data formats for the YouTube Transcriber plugin.

---

## Dependency Check

### `GET|POST /api/plugins/youtube_transcribe/youtube_test`

Check that all required and optional dependencies are available.

**Response (all dependencies available):**
```json
{
    "status": "ok",
    "checks": {
        "yt_dlp": {
            "available": true,
            "version": "2026.03.03"
        },
        "youtube_transcript_api": {
            "available": true,
            "version": "installed"
        },
        "ffmpeg": {
            "available": true,
            "version": "ffmpeg version 8.0.1-3 Copyright (c) 2000-2025 the FFmpeg developers"
        },
        "pillow": {
            "available": true,
            "version": "12.0.0"
        }
    },
    "message": "All dependencies available."
}
```

**Status values:**
| Status | Meaning |
|--------|---------|
| `ok` | All 4 dependencies available |
| `partial` | Core deps (yt-dlp, youtube-transcript-api) OK, optional deps (ffmpeg, Pillow) missing |
| `error` | Core dependencies missing -- plugin will not function |

---

## URL Parsing

The `youtube_client.py` helper parses YouTube URLs into structured data:

**Supported URL formats:**

| Format | Example | Parsed As |
|--------|---------|-----------|
| Standard | `https://www.youtube.com/watch?v=dQw4w9WgXcQ` | video |
| Short | `https://youtu.be/dQw4w9WgXcQ` | video |
| Embed | `https://www.youtube.com/embed/dQw4w9WgXcQ` | video |
| Shorts | `https://www.youtube.com/shorts/dQw4w9WgXcQ` | video |
| Playlist | `https://www.youtube.com/playlist?list=PLxxx` | playlist |
| Video+Playlist | `https://www.youtube.com/watch?v=xxx&list=PLxxx` | video (with playlist_id) |

**Parsed result:**
```python
{
    "type": "video" | "playlist" | "unknown",
    "video_id": "dQw4w9WgXcQ" | None,
    "playlist_id": "PLxxx" | None,
}
```

---

## Transcript Segment Format

Transcripts are internally represented as a list of segments:

```python
[
    {"text": "Hello everyone", "start": 0.0, "duration": 2.5},
    {"text": "welcome to today's video", "start": 2.5, "duration": 3.0},
    {"text": "let me show you this chart", "start": 5.5, "duration": 2.0},
]
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Transcript text for this segment |
| `start` | float | Start time in seconds |
| `duration` | float | Duration in seconds |

### Transcript Sources

**Source 1: youtube-transcript-api (preferred)**

Uses the `YouTubeTranscriptApi` library to fetch captions directly from YouTube. This is the fastest method and requires no video download.

**Source 2: yt-dlp subtitles (fallback)**

Downloads auto-generated or manual subtitles via `yt-dlp` in json3 format. The json3 format contains:

```json
{
    "events": [
        {
            "tStartMs": 0,
            "dDurationMs": 2500,
            "segs": [
                {"utf8": "Hello everyone"}
            ]
        }
    ]
}
```

Events are converted to the standard segment format.

---

## Grouped Sections Format

The `group_segments_by_interval()` function groups segments into time-based sections for `youtube_notes`:

```python
[
    {
        "start": 0,        # Section start (seconds)
        "end": 300,         # Section end (seconds)
        "text": "combined text from all segments in this interval"
    },
    {
        "start": 300,
        "end": 600,
        "text": "next section text..."
    }
]
```

---

## Visual Reference Format

The `detect_visual_references()` function returns detected visual references:

```python
[
    {
        "timestamp": 45.0,
        "text": "if you look at this chart, you can see the growth trend",
        "keyword": "this chart"
    },
    {
        "timestamp": 120.5,
        "text": "as shown in the diagram above",
        "keyword": "as shown"
    }
]
```

---

## Frame Extraction Output

The `extract_frames()` and `extract_frames_at_timestamps()` functions return:

```python
[
    {"path": "/a0/usr/plugins/youtube_transcribe/data/frames_abc123/frame_0000.jpg", "timestamp": 30.0},
    {"path": "/a0/usr/plugins/youtube_transcribe/data/frames_abc123/frame_0001.jpg", "timestamp": 60.0},
]
```

Frames are saved as JPEG at quality level 2 (high quality).

---

## Video Metadata Format

The `get_video_info()` function returns yt-dlp's metadata dictionary. Key fields used:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Video title |
| `channel` | string | Channel name |
| `uploader` | string | Uploader name (fallback for channel) |
| `duration` | int | Duration in seconds |
| `upload_date` | string | Upload date as `YYYYMMDD` |
| `view_count` | int | Number of views |
| `description` | string | Video description (truncated to 500 chars) |

Formatted output example:
```
**Title:** Understanding Machine Learning
**Channel:** Tech Academy
**Duration:** 45:32
**Published:** 2026-01-15
**Views:** 1,234,567
**Description:** In this video we explore the fundamentals of...
```

---

## Output File Naming

All output files are saved to the plugin's `data/` directory with this naming convention:

| Type | Pattern | Example |
|------|---------|---------|
| Transcript | `transcript_<video_id>_<safe_title>.md` | `transcript_dQw4w9WgXcQ_Never_Gonna_Give_You_Up.md` |
| Summary | `summary_<video_id>_<safe_title>.md` | `summary_dQw4w9WgXcQ_Never_Gonna_Give_You_Up.md` |
| Notes | `notes_<video_id>_<safe_title>.md` | `notes_dQw4w9WgXcQ_Never_Gonna_Give_You_Up.md` |
| Playlist | `playlist_<playlist_id>.md` | `playlist_PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf.md` |
| Frames | `frames_<video_id>/frame_NNNN.jpg` | `frames_dQw4w9WgXcQ/frame_0000.jpg` |

Title sanitization: only alphanumeric characters, spaces, hyphens, and underscores are kept. Titles are truncated to 80 characters.

---

## Memory Integration

### Auto-Save Format

When outputs are saved to Agent Zero's memory, they use this format:

**Transcripts:**
```
YouTube Transcript - Video Title [2026-03-08 14:30]

# Transcript: Video Title
**Title:** ...
**Channel:** ...
...
## Full Transcript (450 segments)
[00:00] Hello everyone...
```

**Summaries:**
```
YouTube Summary - Video Title [2026-03-08 14:30]

# Summary: Video Title
**Title:** ...
...
### Overview
[summary content]
```

**Notes:**
```
YouTube Notes - Video Title [2026-03-08 14:30]

# Detailed Notes: Video Title
...
### Section 1 (00:00 - 05:00)
[notes content]
```

### Memory Metadata

Saved memory entries include metadata for retrieval:
- `area`: `"main"`
- `source`: `"youtube_transcribe"`, `"youtube_summary"`, or `"youtube_notes"`

### Fallback Storage

If the memory plugin isn't available, files are written to:
- `memory/youtube_transcripts/transcript_YYYYMMDD_HHMMSS.md`
- `memory/youtube_summaries/summary_YYYYMMDD_HHMMSS.md`
- `memory/youtube_notes/notes_YYYYMMDD_HHMMSS.md`

---

## Response Size Limits

To prevent LLM context window overflow, tool responses are capped:

| Tool | Response Limit | Full Output |
|------|----------------|-------------|
| `youtube_transcribe` | 3,000 chars (preview) | Saved to `data/transcript_*.md` |
| `youtube_summary` | 6,000 chars | Saved to `data/summary_*.md` |
| `youtube_notes` | 6,000 chars | Saved to `data/notes_*.md` |

The response always includes the file path where the full output is stored.

For `youtube_summary`, long transcripts (>12,000 chars) are automatically chunked -- each chunk is summarized separately, then a final synthesis pass combines them into one coherent summary.
