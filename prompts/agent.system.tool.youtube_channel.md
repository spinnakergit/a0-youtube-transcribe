## youtube_channel
Transcribe all videos from a YouTube channel with smart batching. Automatically detects channel size and adjusts its strategy:

- **Small channels** (<=50 videos): Transcribes everything in one pass with a short delay between videos.
- **Medium channels** (51-200 videos): Batches videos into groups of 15, with cooldown periods between batches.
- **Large channels** (200+ videos): Uses smaller batches of 10 with longer delays and 5-minute cooldowns to avoid rate limiting.

Progress is saved to a state file, so the tool can be called again to **resume** where it left off. Videos that fail (e.g., no captions) are tracked separately and can be retried.

**Arguments:**
- **url** (string, required): YouTube channel URL (@handle, /channel/UCxxx, /c/Name, or /user/Name)
- **action** (string): `transcribe` (default), `status` (check progress), or `retry` (re-attempt failed videos)
- **language** (string): Language hint for transcription (e.g., "en", "es")
- **save_to_memory** (string): `true` or `false` (default: `true`)
- **max_videos** (number): Limit how many videos to transcribe in this run (useful for testing or pacing large channels)

~~~json
{"url": "https://www.youtube.com/@ChannelName"}
~~~
~~~json
{"url": "https://www.youtube.com/channel/UCxxxxxxxx", "max_videos": "20"}
~~~
~~~json
{"url": "https://www.youtube.com/@ChannelName", "action": "status"}
~~~
~~~json
{"url": "https://www.youtube.com/@ChannelName", "action": "retry"}
~~~
