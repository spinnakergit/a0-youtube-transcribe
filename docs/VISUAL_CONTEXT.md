# Visual Context Pipeline

How the YouTube Transcriber plugin detects, extracts, and analyzes visual content from videos.

---

## Overview

When speakers reference charts, graphs, slides, or other visual content, the plugin:

1. Detects the reference in the transcript text
2. Extracts a video frame at that timestamp
3. Sends the frame to the LLM for multimodal analysis
4. Annotates the transcript with detailed visual descriptions

This turns a plain transcript into rich study material with context about what was being shown on screen.

---

## Visual Keyword Detection

The plugin scans each transcript segment for these phrases:

| Category | Keywords |
|----------|----------|
| Direct references | "this chart", "this graph", "this slide", "this diagram", "this table", "this figure", "this picture" |
| Pointing | "as you can see", "look at this", "take a look", "if you look at", "let me show you" |
| Screen references | "on the screen", "shown here", "displayed here", "here we can see" |
| Data references | "the data shows", "the table shows", "as shown", "this illustration" |
| General | "looking at the", "in this visual", "the image" |

When a keyword is found, the segment's timestamp and surrounding text are recorded as a visual reference.

### Customizing Keywords

The keyword list is defined in `helpers/youtube_client.py` as the `VISUAL_KEYWORDS` constant. You can add domain-specific keywords by editing this list:

```python
VISUAL_KEYWORDS = [
    "as you can see",
    "this chart",
    # Add your own:
    "on the whiteboard",
    "in this code snippet",
    "the architecture diagram",
]
```

---

## Frame Extraction

### At Visual References (Primary)

When visual references are detected in the transcript:

1. The video is downloaded at the lowest quality sufficient for frame extraction (`yt-dlp -f worst[ext=mp4]`)
2. For each detected timestamp, `ffmpeg` extracts a single frame as JPEG
3. Frames are saved to `data/frames_<video_id>/frame_NNNN.jpg`

```
Transcript: [02:45] "If you look at this chart, you can see the revenue growth..."
    |
    v
ffmpeg -ss 165 -i video.mp4 -frames:v 1 -q:v 2 frame_0000.jpg
    |
    v
Frame saved -> sent to LLM for analysis
```

### Periodic Sampling (Fallback)

When no visual references are detected in the transcript, the plugin falls back to periodic frame extraction:

- Frames are extracted at regular intervals (default: every 30 seconds)
- Maximum frames per video (default: 20)
- A subset (up to 5 frames) is analyzed by the LLM
- Frames showing "just a person talking" with no visual aids are filtered out

This catches visual content that speakers don't explicitly reference.

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `visual.enabled` | `true` | Master switch for visual context extraction |
| `visual.frame_interval` | `30` | Seconds between periodic frame samples |
| `visual.max_frames` | `20` | Maximum frames to extract per video |
| `visual.analyze_frames` | `true` | Whether to send frames to LLM for analysis |

---

## LLM Frame Analysis

### At Visual References

When a frame is extracted at a visual reference, it's sent to the utility LLM with context:

```
System: You are an expert at analyzing visual content from video frames,
        especially charts, graphs, diagrams, and presentation slides.

Message: Analyze this frame from a video at timestamp 02:45.
         The speaker said: "If you look at this chart, you can see the revenue growth..."

         Describe what is shown in detail. If there is a chart, graph, table,
         or diagram, describe its type, axes, data points, trends, and key takeaways.
         If it's a slide, transcribe the text content.
         Be specific and detailed about the visual content.

Attachments: [frame_0000.jpg]
```

The LLM returns a detailed description of the visual content, which is included in the transcript output.

### Periodic Frame Analysis

For periodically sampled frames, the analysis prompt is simpler and includes a filter:

```
System: You analyze video frames for visual content.

Message: Analyze this frame from a video at timestamp 05:00.
         If there is a chart, graph, table, diagram, or presentation slide,
         describe it in detail including type, data, and key takeaways.
         If it's just a person talking with no visual aids, say 'No visual aids displayed.'
```

Frames where the LLM responds with "No visual aids displayed" are filtered out of the output.

---

## Output Format

### Visual References in Transcript

```markdown
## Visual Context Analysis

### [02:45] Visual Content
The frame shows a bar chart titled "Quarterly Revenue Growth (Q1-Q4 2025)".
- X-axis: Quarters (Q1, Q2, Q3, Q4)
- Y-axis: Revenue in millions USD ($0-$50M)
- Q1: $12M, Q2: $18M, Q3: $28M, Q4: $42M
- Clear upward trend with accelerating growth
- Key takeaway: Revenue more than tripled from Q1 to Q4

### [07:12] Visual Content
The frame shows a slide titled "Product Roadmap 2026".
Text content:
- Phase 1 (Q1): API v2 launch, mobile app beta
- Phase 2 (Q2): Enterprise features, SSO integration
- Phase 3 (Q3-Q4): AI assistant, marketplace
```

### Visual References in Notes

When `youtube_notes` detects visual references in a section, it includes them in the notes prompt so the LLM can provide context:

```markdown
#### Visual Content Referenced
- [02:45] The speaker displays a quarterly revenue chart showing growth from
  $12M in Q1 to $42M in Q4 2025, emphasizing the acceleration in Q3-Q4.
  The chart suggests the company achieved product-market fit around mid-year.
```

---

## Requirements

### Required
- `yt-dlp` -- downloads the video for frame extraction
- `ffmpeg` -- extracts individual frames from video

### Optional but Recommended
- `Pillow` -- image handling (used for frame operations)
- A **multimodal LLM** as the utility model -- required to actually analyze frames
  - Works with: GPT-4o, Claude Opus/Sonnet (with vision), Gemini Pro Vision
  - Text-only models will receive frames but cannot interpret them

### Without Frame Analysis

If `ffmpeg` is unavailable or visual extraction is disabled, the plugin still:
- Detects visual keyword references in the transcript text
- Notes the timestamps and speaker's words referencing visuals
- This gives partial context even without frame analysis

---

## Performance Considerations

- **Video download:** The video is downloaded at the lowest quality (`worst[ext=mp4]`) to minimize bandwidth and time
- **Temporary storage:** Videos are downloaded to a temp directory and deleted after frame extraction
- **LLM calls:** Each frame analyzed costs one LLM call. With many visual references, this can add up
- **Periodic sampling:** Only 5 frames (evenly spaced from the extracted set) are analyzed to limit LLM calls
- **Frame files persist:** Extracted frames in `data/frames_<id>/` are kept for reference. Delete manually if storage is a concern

---

## Disabling Visual Context

To disable visual context extraction entirely:

**Via config:**
```yaml
visual:
  enabled: false
```

**Per-request:**
```
"Transcribe this video without visual analysis: [url]"
```

The agent will pass `extract_visuals: false` to the tool.
