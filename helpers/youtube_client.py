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
    """Load plugin config with defaults.

    Returns a plain config dict. For project-aware data routing, pass
    the same `agent` to helper functions that touch the filesystem
    (via _data_dir).
    """
    try:
        config = plugins.get_plugin_config(
            "youtube_transcribe", agent=agent, agent_profile=""
        ) or {}
    except TypeError:
        # Older A0 builds that don't accept agent_profile kwarg
        try:
            config = plugins.get_plugin_config("youtube_transcribe", agent=agent) or {}
        except Exception:
            config = {}
    except Exception:
        config = {}
    return config


def _data_dir(config: dict, agent=None) -> Path:
    """Resolve the data directory for storing transcripts and frames.

    Project isolation is opt-in via the `project_data_isolation` config
    flag (default: True), matching the `_memory` plugin's behaviour.
    Falls back to the existing candidate-list search for the shared
    global dir when no agent/project is available.
    """
    # 1. Try project-scoped path (opt-in, default True)
    try:
        from helpers import plugins as _plugins, projects
        if (
            agent is not None
            and getattr(agent, "context", None) is not None
            and config.get("project_data_isolation", True)
        ):
            project_name = projects.get_context_project_name(agent.context) or ""
            if project_name:
                p = Path(_plugins.determine_plugin_asset_path(
                    "youtube_transcribe", project_name, "", "data"
                ))
                p.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass

    # 2. Fall back to original candidate-list behavior
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
_CHANNEL_RE = re.compile(
    r"youtube\.com/"
    r"(?:@([a-zA-Z0-9_.-]+)"            # @handle
    r"|channel/([a-zA-Z0-9_-]+)"         # /channel/UCxxxx
    r"|c/([a-zA-Z0-9_.-]+)"             # /c/CustomName
    r"|user/([a-zA-Z0-9_.-]+))"         # /user/LegacyName
)


def parse_youtube_url(url: str) -> dict:
    """Parse a YouTube URL and return type info.

    Returns dict with keys:
        type: "video" | "playlist" | "channel" | "unknown"
        video_id: str or None
        playlist_id: str or None
        channel_url: str or None
    """
    url = url.strip()
    result = {"type": "unknown", "video_id": None, "playlist_id": None, "channel_url": None}

    # Check for shorts
    shorts_match = _SHORTS_RE.search(url)
    if shorts_match:
        result["type"] = "video"
        result["video_id"] = shorts_match.group(1)
        return result

    # Check for channel BEFORE video (a channel page may contain ?v= in rare embeds)
    channel_match = _CHANNEL_RE.search(url)
    if channel_match:
        # Only treat as channel if there's no video ID in the URL
        video_match = _VIDEO_RE.search(url)
        if not video_match:
            result["type"] = "channel"
            # Normalise to the canonical URL yt-dlp can resolve
            handle = channel_match.group(1)  # @handle
            chan_id = channel_match.group(2)  # /channel/UCxxx
            custom = channel_match.group(3)  # /c/Name
            user = channel_match.group(4)    # /user/Name
            if handle:
                result["channel_url"] = f"https://www.youtube.com/@{handle}"
            elif chan_id:
                result["channel_url"] = f"https://www.youtube.com/channel/{chan_id}"
            elif custom:
                result["channel_url"] = f"https://www.youtube.com/c/{custom}"
            elif user:
                result["channel_url"] = f"https://www.youtube.com/user/{user}"
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
# Channel enumeration
# ---------------------------------------------------------------------------

def _readable_channel_name(channel_url: str) -> str:
    """Extract a human-readable name from a channel URL as a fallback.

    '@verifiedinvesting' -> 'verifiedinvesting'
    '/channel/UCxxx' -> 'UCxxx'
    '/c/SomeName' -> 'SomeName'
    """
    match = _CHANNEL_RE.search(channel_url)
    if match:
        return match.group(1) or match.group(2) or match.group(3) or match.group(4) or "Unknown"
    # Last resort: grab the last path segment
    stripped = channel_url.rstrip("/")
    return stripped.rsplit("/", 1)[-1].lstrip("@") or "Unknown"


def get_channel_info(channel_url: str) -> dict:
    """Get channel metadata (name, video count estimate) via yt-dlp.

    Returns dict with keys: channel, channel_id, channel_url, video_count, description.
    video_count is the number of entries yt-dlp finds on the channel page.
    """
    # Append /videos to get the uploads tab directly
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"

    # First try a non-flat single-video dump to get rich channel metadata
    meta_cmd = [
        "yt-dlp", "--dump-json", "--no-download",
        "--no-warnings", "--quiet",
        "--playlist-items", "1",
        url,
    ]
    result = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=120)

    fallback_name = _readable_channel_name(channel_url)
    info = {"channel": fallback_name, "channel_id": "", "channel_url": channel_url,
            "video_count": 0, "description": ""}
    if result.returncode == 0 and result.stdout.strip():
        first_line = result.stdout.strip().split("\n")[0]
        try:
            data = json.loads(first_line)
            info["channel"] = data.get("channel") or data.get("uploader") or fallback_name
            info["channel_id"] = data.get("channel_id") or ""
        except json.JSONDecodeError:
            pass

    # Count total videos with a separate fast pass
    count_cmd = [
        "yt-dlp", "--flat-playlist",
        "--print", "id",
        "--no-warnings", "--quiet",
        url,
    ]
    count_result = subprocess.run(count_cmd, capture_output=True, text=True, timeout=300)
    if count_result.returncode == 0:
        lines = [l for l in count_result.stdout.strip().split("\n") if l.strip()]
        info["video_count"] = len(lines)

    return info


def get_channel_videos(channel_url: str, max_videos: int = 0) -> list[dict]:
    """Get all video entries for a channel's uploads.

    Returns list of dicts with at least: id, title, url.
    Set max_videos=0 for unlimited.
    """
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"

    cmd = [
        "yt-dlp", "--dump-json", "--no-download",
        "--no-warnings", "--quiet",
        "--flat-playlist",
    ]
    if max_videos > 0:
        cmd += ["--playlist-end", str(max_videos)]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp channel enumeration failed: {result.stderr.strip()}")

    videos = []
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            try:
                info = json.loads(line)
                videos.append(info)
            except json.JSONDecodeError:
                continue
    return videos


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------

def get_transcript_captions(video_id: str, language: str = "") -> Optional[list[dict]]:
    """Try to get transcript from YouTube captions via youtube-transcript-api.

    Supports both youtube-transcript-api 1.x (instance .fetch) and 0.x
    (classmethod .get_transcript). Returns list of dicts:
    [{"text": "...", "start": 0.0, "duration": 2.5}, ...] or None.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return None

    languages = [language] if language else ["en"]

    # 1.x path: instance method .fetch() returns FetchedTranscript with snippets
    fetch = getattr(YouTubeTranscriptApi, "fetch", None)
    if callable(fetch):
        try:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=languages)
            # FetchedTranscript is iterable of FetchedTranscriptSnippet objects
            # with .text, .start, .duration attributes. Fall back to dict() if
            # the library returns legacy shape.
            out: list[dict] = []
            for snip in fetched:
                if hasattr(snip, "text") and hasattr(snip, "start"):
                    out.append({
                        "text": snip.text,
                        "start": float(snip.start),
                        "duration": float(getattr(snip, "duration", 0.0) or 0.0),
                    })
                elif isinstance(snip, dict):
                    out.append(snip)
            return out or None
        except Exception:
            pass  # fall through to legacy path

    # 0.x path: classmethod .get_transcript()
    get_transcript = getattr(YouTubeTranscriptApi, "get_transcript", None)
    if callable(get_transcript):
        try:
            return get_transcript(video_id, languages=languages)
        except Exception:
            return None

    return None


def get_transcript_ytdlp(video_url: str, language: str = "") -> Optional[list[dict]]:
    """Fallback: extract subtitles via yt-dlp.

    Downloads auto-generated or manual subtitles in JSON format.
    Returns list of dicts with text/start/duration, or None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_file = os.path.join(tmpdir, "subs")
        ytdlp_bin = shutil.which("yt-dlp") or "yt-dlp"
        cmd = [
            ytdlp_bin,
            "--write-auto-subs", "--write-subs",
            "--sub-format", "json3",
            "--skip-download",
            "--no-warnings",
            "-o", sub_file,
        ]
        if language:
            cmd += ["--sub-langs", language]
        else:
            cmd += ["--sub-langs", "en.*,en"]
        cmd.append(video_url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            import logging
            logging.getLogger("youtube_transcribe").warning(
                "yt-dlp binary not found on PATH; subtitle fallback unavailable"
            )
            return None

        # Find the subtitle file
        sub_files = list(Path(tmpdir).glob("*.json3"))
        if not sub_files:
            sub_files = list(Path(tmpdir).glob("*.json"))
        if not sub_files:
            import logging
            log = logging.getLogger("youtube_transcribe")
            log.warning(
                "yt-dlp returned no subtitle file (rc=%s). stderr=%s",
                result.returncode,
                (result.stderr or "").strip()[:500],
            )
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
