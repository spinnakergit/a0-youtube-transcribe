## youtube_transcribe
Transcribe a YouTube video or playlist. Extracts text from audio using YouTube captions, detects visual references (charts, graphs, slides), and extracts/analyzes video frames for context.

**Arguments:**
- **url** (string, required): YouTube video or playlist URL
- **action** (string): `transcribe` (default) for single video, `playlist` for playlist mode
- **extract_visuals** (string): `true` or `false` — extract and analyze video frames at visual references (default: from config)
- **language** (string): Language hint for transcription (e.g., "en", "es")
- **save_to_memory** (string): `true` or `false` (default: `true`)
- **max_videos** (number): Max videos to process from a playlist (default: 10)

~~~json
{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
~~~
~~~json
{"url": "https://www.youtube.com/playlist?list=PLxxx", "action": "playlist", "max_videos": "5"}
~~~
~~~json
{"url": "https://youtu.be/abc123", "extract_visuals": "true", "language": "en"}
~~~
