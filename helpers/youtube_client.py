"""YouTube client helper for the YouTube Transcriber plugin.

Handles:
- URL parsing (video vs playlist)
- Video metadata extraction
- Transcript retrieval (YouTube captions -> yt-dlp subtitles fallback)
- Audio download via yt-dlp
- Frame extraction via ffmpeg
- Playlist resolution
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import plugins


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_yt_config(agent=None):
    """Load plugin config with defaults."""
    try:
        config = plugins.get_plugin_config("youtube_transcribe", agent=agent) or {}
    except Exception:
        config = {}
    return config


def _data_dir(config: dict) -> Path:
    """Resolve the data directory for storing transcripts and frames."""
    rel = config.get("data_dir", "data")
    candidates = [
        Path(__file__).parent.parent / rel,
        Path("/a0/usr/plugins/youtube_transcribe") / rel,
        Path("/git/agent-zero/usr/plugins/youtube_transcribe") / rel,
    ]
    for p in candidates:
        if p.parent.exists():
            p.mkdir(parents=True, exist_ok=True)
            return p
    fallback = Path(tempfile.gettempdir()) / "yt_transcribe_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

_VIDEO_RE = re.compile(
    r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)"
    r"([a-zA-Z0-9_-]{11})"
)
_PLAYLIST_RE = re.compile(r"[?&]list=([a-zA-Z0-9_-]+)")
_SHORTS_RE = re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})")


def parse_youtube_url(url: str) -> dict:
    """Parse a YouTube URL and return type info.

    Returns dict with keys:
        type: "video" | "playlist" | "unknown"
        video_id: str or None
        playlist_id: str or None
    """
    url = url.strip()
    result = {"type": "unknown", "video_id": None, "playlist_id": None}

    # Check for shorts
    shorts_match = _SHORTS_RE.search(url)
    if shorts_match:
        result["type"] = "video"
        result["video_id"] = shorts_match.group(1)
        return result

    # Check for video
    video_match = _VIDEO_RE.search(url)
    if video_match:
        result["video_id"] = video_match.group(1)
        result["type"] = "video"

    # Check for playlist
    playlist_match = _PLAYLIST_RE.search(url)
    if playlist_match:
        result["playlist_id"] = playlist_match.group(1)
        if not result["video_id"]:
            result["type"] = "playlist"

    return result


# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------

def get_video_info(url: str) -> dict:
    """Get video metadata via yt-dlp without downloading."""
    cmd = [
        "yt-dlp", "--dump-json", "--no-download",
        "--no-warnings", "--quiet",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def get_playlist_videos(playlist_url: str, max_videos: int = 10) -> list[dict]:
    """Get metadata for all videos in a playlist."""
    cmd = [
        "yt-dlp", "--dump-json", "--no-download",
        "--no-warnings", "--quiet",
        "--flat-playlist",
        playlist_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp playlist failed: {result.stderr.strip()}")

    videos = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            try:
                info = json.loads(line)
                videos.append(info)
            except json.JSONDecodeError:
                continue
    if max_videos > 0:
        videos = videos[:max_videos]
    return videos


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------

def get_transcript_captions(video_id: str, language: str = "") -> Optional[list[dict]]:
    """Try to get transcript from YouTube captions via youtube-transcript-api.

    Returns list of dicts: [{"text": "...", "start": 0.0, "duration": 2.5}, ...]
    Returns None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        if language:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        else:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return transcript
    except Exception:
        return None


def get_transcript_ytdlp(video_url: str, language: str = "") -> Optional[list[dict]]:
    """Fallback: extract subtitles via yt-dlp.

    Downloads auto-generated or manual subtitles in JSON format.
    Returns list of dicts with text/start/duration, or None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_file = os.path.join(tmpdir, "subs")
        cmd = [
            "yt-dlp",
            "--write-auto-subs", "--write-subs",
            "--sub-format", "json3",
            "--skip-download",
            "--no-warnings", "--quiet",
            "-o", sub_file,
        ]
        if language:
            cmd += ["--sub-langs", language]
        else:
            cmd += ["--sub-langs", "en.*,en"]
        cmd.append(video_url)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        # Find the subtitle file
        sub_files = list(Path(tmpdir).glob("*.json3"))
        if not sub_files:
            sub_files = list(Path(tmpdir).glob("*.json"))
        if not sub_files:
            return None

        with open(sub_files[0], "r") as f:
            data = json.load(f)

        # json3 format has "events" array
        events = data.get("events", [])
        segments = []
        for event in events:
            segs = event.get("segs", [])
            text = "".join(s.get("utf8", "") for s in segs).strip()
            if text and text != "\n":
                start_ms = event.get("tStartMs", 0)
                dur_ms = event.get("dDurationMs", 0)
                segments.append({
                    "text": text,
                    "start": start_ms / 1000.0,
                    "duration": dur_ms / 1000.0,
                })
        return segments if segments else None


def get_transcript(video_id: str, video_url: str, language: str = "") -> list[dict]:
    """Get transcript using best available method.

    Tries YouTube captions first, then yt-dlp subtitle extraction.
    Returns list of segments or raises RuntimeError.
    """
    # Try YouTube captions API first (fastest)
    segments = get_transcript_captions(video_id, language)
    if segments:
        return segments

    # Fallback to yt-dlp subtitle download
    segments = get_transcript_ytdlp(video_url, language)
    if segments:
        return segments

    raise RuntimeError(
        f"No transcript available for video {video_id}. "
        "The video may not have captions or auto-generated subtitles."
    )


# ---------------------------------------------------------------------------
# Transcript formatting
# ---------------------------------------------------------------------------

def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_transcript(segments: list[dict], include_timestamps: bool = True) -> str:
    """Format transcript segments into readable text."""
    lines = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        if include_timestamps:
            ts = format_timestamp(seg["start"])
            lines.append(f"[{ts}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def group_segments_by_interval(segments: list[dict], interval_seconds: int = 300) -> list[dict]:
    """Group transcript segments into time-based sections.

    Returns list of dicts: [{"start": 0, "end": 300, "text": "combined text"}, ...]
    """
    if not segments:
        return []

    groups = []
    current_start = 0
    current_texts = []

    for seg in segments:
        seg_start = seg["start"]
        # Check if we've crossed into a new interval
        while seg_start >= current_start + interval_seconds:
            if current_texts:
                groups.append({
                    "start": current_start,
                    "end": current_start + interval_seconds,
                    "text": " ".join(current_texts),
                })
            current_texts = []
            current_start += interval_seconds

        current_texts.append(seg["text"].strip())

    # Final group
    if current_texts:
        groups.append({
            "start": current_start,
            "end": current_start + interval_seconds,
            "text": " ".join(current_texts),
        })

    return groups


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames(
    video_url: str,
    output_dir: str,
    interval: int = 30,
    max_frames: int = 20,
) -> list[dict]:
    """Extract frames from a video at regular intervals.

    Downloads the video temporarily, extracts frames with ffmpeg.
    Returns list of dicts: [{"path": "/path/to/frame.jpg", "timestamp": 30.0}, ...]
    """
    if not shutil.which("ffmpeg"):
        return []

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")

        # Download video (lowest quality sufficient for frame extraction)
        cmd = [
            "yt-dlp",
            "-f", "worst[ext=mp4]/worst",
            "--no-warnings", "--quiet",
            "-o", video_path,
            video_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0 or not os.path.exists(video_path):
            return []

        # Get video duration
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", video_path,
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        try:
            duration = float(json.loads(probe.stdout)["format"]["duration"])
        except (json.JSONDecodeError, KeyError):
            duration = 600  # default 10 min

        # Calculate timestamps to extract
        timestamps = []
        t = float(interval)
        while t < duration and len(timestamps) < max_frames:
            timestamps.append(t)
            t += interval

        # Extract each frame
        frames = []
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(output_dir, f"frame_{i:04d}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(ts),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                frame_path,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and os.path.exists(frame_path):
                frames.append({"path": frame_path, "timestamp": ts})

        return frames


def extract_frames_at_timestamps(
    video_url: str,
    output_dir: str,
    timestamps: list[float],
) -> list[dict]:
    """Extract frames at specific timestamps (e.g., when visuals are referenced)."""
    if not shutil.which("ffmpeg") or not timestamps:
        return []

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")

        cmd = [
            "yt-dlp",
            "-f", "worst[ext=mp4]/worst",
            "--no-warnings", "--quiet",
            "-o", video_path,
            video_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0 or not os.path.exists(video_path):
            return []

        frames = []
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(output_dir, f"frame_{i:04d}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(ts),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                frame_path,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and os.path.exists(frame_path):
                frames.append({"path": frame_path, "timestamp": ts})

        return frames


# ---------------------------------------------------------------------------
# Visual reference detection
# ---------------------------------------------------------------------------

# Phrases that typically indicate the speaker is referencing a visual
VISUAL_KEYWORDS = [
    "as you can see", "look at this", "this chart", "this graph", "this slide",
    "this diagram", "on the screen", "shown here", "displayed here",
    "take a look", "if you look at", "the table shows", "this figure",
    "as shown", "the image", "this picture", "on this slide",
    "let me show you", "here we can see", "this illustration",
    "the data shows", "looking at the", "in this visual",
]


def detect_visual_references(segments: list[dict]) -> list[dict]:
    """Scan transcript segments for references to visual content.

    Returns list of dicts: [{"timestamp": 45.0, "text": "as you can see on this chart...", "keyword": "this chart"}, ...]
    """
    references = []
    for seg in segments:
        text_lower = seg["text"].lower()
        for keyword in VISUAL_KEYWORDS:
            if keyword in text_lower:
                references.append({
                    "timestamp": seg["start"],
                    "text": seg["text"],
                    "keyword": keyword,
                })
                break  # One match per segment
    return references


# ---------------------------------------------------------------------------
# Metadata formatting
# ---------------------------------------------------------------------------

def format_video_info(info: dict) -> str:
    """Format video metadata into a readable header."""
    title = info.get("title", "Unknown")
    channel = info.get("channel", info.get("uploader", "Unknown"))
    duration = info.get("duration", 0)
    upload_date = info.get("upload_date", "")
    view_count = info.get("view_count", 0)
    description = info.get("description", "")[:500]

    dur_str = format_timestamp(duration) if duration else "Unknown"
    date_str = ""
    if upload_date and len(upload_date) == 8:
        date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

    lines = [
        f"**Title:** {title}",
        f"**Channel:** {channel}",
        f"**Duration:** {dur_str}",
    ]
    if date_str:
        lines.append(f"**Published:** {date_str}")
    if view_count:
        lines.append(f"**Views:** {view_count:,}")
    if description:
        lines.append(f"**Description:** {description}")

    return "\n".join(lines)
