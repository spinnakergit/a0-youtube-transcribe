## youtube_notes
Generate detailed, timestamped study notes from a YouTube video. Breaks the video into sections and creates comprehensive notes for each, with special attention to visual references (charts, graphs, slides).

**Arguments:**
- **url** (string): YouTube video URL (will auto-extract transcript)
- **transcript** (string): Pre-extracted transcript text (use instead of url if you already have the transcript)
- **section_minutes** (number): Length of each section in minutes (default: 5)
- **language** (string): Language hint for transcription
- **save_to_memory** (string): `true` or `false` (default: `true`)

~~~json
{"url": "https://www.youtube.com/watch?v=abc123"}
~~~
~~~json
{"url": "https://youtu.be/abc123", "section_minutes": "10"}
~~~
~~~json
{"transcript": "[00:00] Hello...", "save_to_memory": "false"}
~~~
