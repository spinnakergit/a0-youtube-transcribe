---
name: "youtube-research"
description: "Research and analyze YouTube video content. Get summaries, detailed notes, and insights from video transcripts."
version: "1.0.0"
author: "YouTube Transcriber Plugin"
license: "MIT"
tags: ["youtube", "research", "summarization", "knowledge"]
triggers:
  - "youtube research"
  - "summarize youtube"
  - "youtube summary"
  - "youtube notes"
  - "analyze youtube"
  - "study youtube"
  - "notes from video"
allowed_tools:
  - youtube_transcribe
  - youtube_summary
  - youtube_notes
metadata:
  complexity: "intermediate"
  category: "research"
---

# YouTube Research Skill

Use YouTube tools to extract knowledge from video content.

## Workflow

1. **Quick summary** of a video:
   `youtube_summary` with `url: VIDEO_URL`

2. **Detailed study notes** with timestamps:
   `youtube_notes` with `url: VIDEO_URL`, `section_minutes: 5`

3. **Full transcript** for deep analysis:
   `youtube_transcribe` with `url: VIDEO_URL`

4. **Research a playlist** on a topic:
   `youtube_transcribe` with `url: PLAYLIST_URL`, `action: playlist`
   Then `youtube_summary` on each video of interest

## Tips
- Start with `youtube_summary` for a quick overview
- Use `youtube_notes` with smaller `section_minutes` for more granular notes
- Visual references (charts, graphs) are automatically detected and annotated
- All content auto-saves to memory for future reference
- Chain tools: transcribe first, then summarize or generate notes from the transcript
