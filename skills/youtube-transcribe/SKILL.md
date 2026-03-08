---
name: "youtube-transcribe"
description: "Transcribe YouTube videos and playlists. Extract audio to text with visual context, generate summaries and detailed notes."
version: "1.0.0"
author: "YouTube Transcriber Plugin"
license: "MIT"
tags: ["youtube", "transcription", "video", "audio"]
triggers:
  - "transcribe youtube"
  - "youtube transcript"
  - "transcribe video"
  - "youtube to text"
  - "video transcript"
  - "transcribe playlist"
allowed_tools:
  - youtube_transcribe
  - youtube_summary
  - youtube_notes
metadata:
  complexity: "intermediate"
  category: "transcription"
---

# YouTube Transcribe Skill

Transcribe YouTube videos and playlists with visual context extraction.

## Workflow

1. **Transcribe a single video:**
   `youtube_transcribe` with `url: VIDEO_URL`

2. **Transcribe with visual analysis:**
   `youtube_transcribe` with `url: VIDEO_URL`, `extract_visuals: true`

3. **Transcribe a playlist:**
   `youtube_transcribe` with `url: PLAYLIST_URL`, `action: playlist`, `max_videos: 10`

4. **Generate a summary:**
   `youtube_summary` with `url: VIDEO_URL`

5. **Generate detailed notes:**
   `youtube_notes` with `url: VIDEO_URL`, `section_minutes: 5`

## Tips
- Use `youtube_transcribe` first to get the raw transcript
- Follow with `youtube_summary` for a concise overview
- Use `youtube_notes` for deep study material with section-by-section breakdown
- Visual context extraction detects chart/graph references and extracts frames
- All results auto-save to memory by default
- Supports YouTube Shorts, standard videos, and playlists
