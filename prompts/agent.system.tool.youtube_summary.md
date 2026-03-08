## youtube_summary
Generate an AI-powered summary of a YouTube video. Extracts the transcript, then uses the LLM to create a structured summary with main topics, key points, data/evidence, and conclusions.

**Arguments:**
- **url** (string): YouTube video URL (will auto-extract transcript)
- **transcript** (string): Pre-extracted transcript text (use instead of url if you already have the transcript)
- **language** (string): Language hint for transcription
- **save_to_memory** (string): `true` or `false` (default: `true`)

~~~json
{"url": "https://www.youtube.com/watch?v=abc123"}
~~~
~~~json
{"transcript": "[00:00] Hello everyone...", "save_to_memory": "true"}
~~~
