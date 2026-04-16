import asyncio
import json
import time
from pathlib import Path
from helpers.tool import Tool, Response
from usr.plugins.youtube_transcribe.helpers.youtube_client import (
    parse_youtube_url,
    get_channel_info,
    get_channel_videos,
    get_transcript,
    format_transcript,
    format_timestamp,
    get_yt_config,
    _data_dir,
)


# ---------------------------------------------------------------------------
# Channel state persistence (resumable progress tracker)
# ---------------------------------------------------------------------------

class ChannelState:
    """Tracks transcription progress for a channel so work can be resumed.

    State file lives alongside transcripts in the data dir:
        data/channel_<channel_id>_state.json

    Schema:
        channel_url, channel_name, channel_id,
        total_videos, video_ids (ordered list),
        completed (list of video IDs done),
        failed (dict video_id -> error message),
        current_batch, strategy, started_at, updated_at
    """

    def __init__(self, state_path: Path):
        self.path = state_path
        self.data: dict = {}

    @classmethod
    def load_or_create(
        cls,
        data_dir: Path,
        channel_id: str,
        channel_url: str,
        channel_name: str,
        video_list: list[dict],
        strategy: str,
    ) -> "ChannelState":
        state_path = data_dir / f"channel_{channel_id}_state.json"
        cs = cls(state_path)

        if state_path.exists():
            try:
                cs.data = json.loads(state_path.read_text(encoding="utf-8"))
                # Refresh video list in case channel added new uploads
                existing_ids = set(cs.data.get("video_ids", []))
                new_ids = [v.get("id", v.get("url", "")) for v in video_list]
                for vid in new_ids:
                    if vid and vid not in existing_ids:
                        cs.data["video_ids"].append(vid)
                cs.data["total_videos"] = len(cs.data["video_ids"])
                cs.data["updated_at"] = _now()
                cs.save()
                return cs
            except (json.JSONDecodeError, KeyError):
                pass  # Corrupt state — rebuild

        cs.data = {
            "channel_url": channel_url,
            "channel_name": channel_name,
            "channel_id": channel_id,
            "total_videos": len(video_list),
            "video_ids": [v.get("id", v.get("url", "")) for v in video_list],
            "video_titles": {
                v.get("id", v.get("url", "")): v.get("title", "Untitled")
                for v in video_list
            },
            "completed": [],
            "failed": {},
            "current_batch": 0,
            "strategy": strategy,
            "started_at": _now(),
            "updated_at": _now(),
        }
        cs.save()
        return cs

    def save(self):
        self.data["updated_at"] = _now()
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @property
    def remaining_ids(self) -> list[str]:
        done = set(self.data.get("completed", []))
        failed = set(self.data.get("failed", {}).keys())
        return [v for v in self.data["video_ids"] if v not in done and v not in failed]

    def mark_done(self, video_id: str):
        if video_id not in self.data["completed"]:
            self.data["completed"].append(video_id)
        self.save()

    def mark_failed(self, video_id: str, error: str):
        self.data["failed"][video_id] = error
        self.save()

    def advance_batch(self):
        self.data["current_batch"] += 1
        self.save()

    @property
    def progress_str(self) -> str:
        total = self.data["total_videos"]
        done = len(self.data["completed"])
        failed = len(self.data["failed"])
        remaining = total - done - failed
        return f"{done}/{total} done, {failed} failed, {remaining} remaining"

    def title_for(self, video_id: str) -> str:
        return self.data.get("video_titles", {}).get(video_id, video_id)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Size classification
# ---------------------------------------------------------------------------

def classify_channel(video_count: int, config: dict) -> str:
    """Return 'small', 'medium', or 'large' based on thresholds."""
    ch_cfg = config.get("channel", {})
    small_max = ch_cfg.get("small_threshold", 50)
    large_min = ch_cfg.get("large_threshold", 200)
    if video_count <= small_max:
        return "small"
    if video_count > large_min:
        return "large"
    return "medium"


def get_batch_params(strategy: str, config: dict) -> tuple[int, float, float]:
    """Return (batch_size, delay_per_video, cooldown_between_batches) for a strategy."""
    ch_cfg = config.get("channel", {})
    if strategy == "small":
        return (
            ch_cfg.get("batch_size_small", 0),
            ch_cfg.get("delay_per_video", 3),
            0,
        )
    if strategy == "medium":
        return (
            ch_cfg.get("batch_size_medium", 15),
            ch_cfg.get("delay_per_video_medium", 5),
            ch_cfg.get("batch_cooldown_medium", 60),
        )
    # large
    return (
        ch_cfg.get("batch_size_large", 10),
        ch_cfg.get("delay_per_video_large", 8),
        ch_cfg.get("batch_cooldown_large", 300),
    )


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

class YouTubeChannel(Tool):
    """Transcribe all videos from a YouTube channel with smart batching."""

    async def execute(self, **kwargs) -> Response:
        url = self.args.get("url", "")
        action = self.args.get("action", "transcribe")

        if not url:
            return Response(
                message="Error: url is required. Provide a YouTube channel URL "
                        "(e.g. https://www.youtube.com/@ChannelName).",
                break_loop=False,
            )

        config = get_yt_config(self.agent)
        parsed = parse_youtube_url(url)

        if parsed["type"] != "channel":
            return Response(
                message="Error: URL does not look like a YouTube channel. "
                        "Expected a URL like https://www.youtube.com/@ChannelName, "
                        "/channel/UCxxx, /c/Name, or /user/Name.\n\n"
                        "For single videos use `youtube_transcribe`, "
                        "for playlists use `youtube_transcribe` with action=playlist.",
                break_loop=False,
            )

        channel_url = parsed["channel_url"]

        # --- Action: status (check progress of an ongoing job) ---
        if action == "status":
            return self._report_status(config, channel_url)

        # --- Action: retry (re-attempt previously failed videos) ---
        if action == "retry":
            return await self._retry_failed(config, channel_url)

        # --- Action: transcribe (default) ---
        return await self._transcribe_channel(config, channel_url)

    # ------------------------------------------------------------------
    # Main transcription flow
    # ------------------------------------------------------------------

    async def _transcribe_channel(self, config: dict, channel_url: str) -> Response:
        # Step 1: Probe the channel
        self.set_progress("Scanning channel...")
        try:
            ch_info = get_channel_info(channel_url)
        except Exception as e:
            return Response(message=f"Error scanning channel: {e}", break_loop=False)

        channel_name = ch_info.get("channel") or ch_info.get("channel_url", "Unknown")
        video_count = ch_info.get("video_count", 0)
        channel_id = ch_info.get("channel_id") or _slug(channel_name)

        if video_count == 0:
            return Response(
                message=f"Channel **{channel_name}** appears to have no public videos.",
                break_loop=False,
            )

        strategy = classify_channel(video_count, config)
        batch_size, delay, cooldown = get_batch_params(strategy, config)

        # Step 2: Enumerate all videos
        self.set_progress(f"Enumerating {video_count} videos on {channel_name}...")
        try:
            video_list = get_channel_videos(channel_url)
        except Exception as e:
            return Response(message=f"Error listing channel videos: {e}", break_loop=False)

        if not video_list:
            return Response(
                message=f"Could not retrieve video list for **{channel_name}**.",
                break_loop=False,
            )

        # Step 3: Load or create state
        data_dir = _data_dir(config, agent=self.agent)
        state = ChannelState.load_or_create(
            data_dir, channel_id, channel_url, channel_name, video_list, strategy,
        )

        remaining = state.remaining_ids
        if not remaining:
            return Response(
                message=f"All {state.data['total_videos']} videos on **{channel_name}** "
                        f"have already been transcribed! ({state.progress_str})\n\n"
                        f"State file: `{state.path}`",
                break_loop=False,
            )

        # Step 4: Report the plan
        plan_lines = [
            f"# Channel Transcription: {channel_name}",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total videos | {state.data['total_videos']} |",
            f"| Already done | {len(state.data['completed'])} |",
            f"| Failed (will skip) | {len(state.data['failed'])} |",
            f"| Remaining | {len(remaining)} |",
            f"| Strategy | **{strategy}** |",
            f"| Batch size | {batch_size if batch_size else 'all at once'} |",
            f"| Delay between videos | {delay}s |",
            f"| Cooldown between batches | {cooldown}s |",
            f"",
        ]

        # Step 5: Process videos
        language = self.args.get("language", config.get("transcription", {}).get("language", ""))
        include_timestamps = config.get("output", {}).get("include_timestamps", True)
        save_to_memory = self.args.get("save_to_memory", "true").lower() == "true"
        skip_no_captions = config.get("channel", {}).get("skip_no_captions", True)
        max_videos_arg = self.args.get("max_videos", "")

        # Allow limiting how many to do this run
        max_this_run = int(max_videos_arg) if max_videos_arg else 0
        videos_to_process = remaining
        if max_this_run > 0:
            videos_to_process = remaining[:max_this_run]

        # Batching logic
        if batch_size and batch_size > 0:
            batches = [
                videos_to_process[i:i + batch_size]
                for i in range(0, len(videos_to_process), batch_size)
            ]
        else:
            batches = [videos_to_process]

        transcribed = 0
        skipped = 0
        errors = 0
        batch_summaries = []

        for batch_idx, batch in enumerate(batches):
            state.advance_batch()
            batch_start = time.time()
            batch_done = 0
            batch_err = 0

            self.set_progress(
                f"Batch {batch_idx + 1}/{len(batches)} — "
                f"{len(batch)} videos — overall {state.progress_str}"
            )

            for vid_idx, video_id in enumerate(batch):
                vid_title = state.title_for(video_id)
                vid_url = f"https://www.youtube.com/watch?v={video_id}"

                self.set_progress(
                    f"[{batch_idx+1}/{len(batches)}] "
                    f"Video {vid_idx+1}/{len(batch)}: {vid_title[:50]}..."
                )

                try:
                    segments = get_transcript(video_id, vid_url, language)
                except RuntimeError:
                    if skip_no_captions:
                        state.mark_failed(video_id, "no_captions")
                        skipped += 1
                        continue
                    else:
                        state.mark_failed(video_id, "no_captions")
                        errors += 1
                        continue
                except Exception as e:
                    state.mark_failed(video_id, str(e))
                    errors += 1
                    continue

                transcript_text = format_transcript(segments, include_timestamps)

                # Save transcript file
                safe_title = "".join(
                    c if c.isalnum() or c in " -_" else "" for c in vid_title
                )[:80].strip()
                file_path = data_dir / f"transcript_{video_id}_{safe_title}.md"
                file_path.write_text(
                    f"# {vid_title}\n\nVideo ID: {video_id}\nChannel: {channel_name}\n\n{transcript_text}",
                    encoding="utf-8",
                )

                # Save to memory
                if save_to_memory:
                    timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
                    memory_text = (
                        f"YouTube Transcript - {vid_title} "
                        f"(Channel: {channel_name}) [{timestamp}]\n\n{transcript_text}"
                    )
                    await _save_to_memory(self.agent, memory_text)

                state.mark_done(video_id)
                transcribed += 1
                batch_done += 1

                # Throttle between videos
                if vid_idx < len(batch) - 1:
                    await asyncio.sleep(delay)

            batch_elapsed = time.time() - batch_start
            batch_summaries.append(
                f"- Batch {batch_idx+1}: {batch_done} transcribed, "
                f"{batch_err} errors, {batch_elapsed:.0f}s"
            )

            # Cooldown between batches (but not after the last one)
            if cooldown > 0 and batch_idx < len(batches) - 1:
                self.set_progress(
                    f"Cooling down {cooldown}s before next batch... ({state.progress_str})"
                )
                await asyncio.sleep(cooldown)

        # Step 6: Final report
        report_lines = plan_lines + [
            f"## Results",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Transcribed this run | {transcribed} |",
            f"| Skipped (no captions) | {skipped} |",
            f"| Errors | {errors} |",
            f"| Overall progress | {state.progress_str} |",
            f"",
            f"## Batch Details",
        ] + batch_summaries + [
            f"",
            f"**State file:** `{state.path}`",
            f"**Transcripts saved to:** `{data_dir}/`",
        ]

        if state.remaining_ids:
            report_lines.append(
                f"\n**{len(state.remaining_ids)} videos remaining.** "
                f"Run this tool again with the same channel URL to continue."
            )
        else:
            report_lines.append(f"\nAll videos on **{channel_name}** have been transcribed!")

        if save_to_memory:
            report_lines.append("[Transcripts also saved to memory (vector DB)]")

        return Response(message="\n".join(report_lines), break_loop=False)

    # ------------------------------------------------------------------
    # Status check
    # ------------------------------------------------------------------

    def _report_status(self, config: dict, channel_url: str) -> Response:
        data_dir = _data_dir(config, agent=self.agent)

        # Find matching state file
        state_files = list(data_dir.glob("channel_*_state.json"))
        for sf in state_files:
            try:
                d = json.loads(sf.read_text(encoding="utf-8"))
                if d.get("channel_url") == channel_url:
                    total = d["total_videos"]
                    done = len(d.get("completed", []))
                    failed = len(d.get("failed", {}))
                    remaining = total - done - failed
                    lines = [
                        f"# Channel Status: {d.get('channel_name', 'Unknown')}",
                        f"",
                        f"| Metric | Value |",
                        f"|--------|-------|",
                        f"| Total videos | {total} |",
                        f"| Completed | {done} |",
                        f"| Failed | {failed} |",
                        f"| Remaining | {remaining} |",
                        f"| Strategy | {d.get('strategy', '?')} |",
                        f"| Started | {d.get('started_at', '?')} |",
                        f"| Last update | {d.get('updated_at', '?')} |",
                        f"",
                        f"**State file:** `{sf}`",
                    ]
                    if failed:
                        lines.append(f"\n**Failed videos:** Use `action=retry` to re-attempt them.")
                    if remaining:
                        lines.append(
                            f"\n**{remaining} videos remaining.** "
                            f"Run with `action=transcribe` to continue."
                        )
                    return Response(message="\n".join(lines), break_loop=False)
            except (json.JSONDecodeError, KeyError):
                continue

        return Response(
            message=f"No transcription state found for {channel_url}. "
                    f"Run with `action=transcribe` to start.",
            break_loop=False,
        )

    # ------------------------------------------------------------------
    # Retry failed videos
    # ------------------------------------------------------------------

    async def _retry_failed(self, config: dict, channel_url: str) -> Response:
        data_dir = _data_dir(config, agent=self.agent)
        language = self.args.get("language", config.get("transcription", {}).get("language", ""))
        include_timestamps = config.get("output", {}).get("include_timestamps", True)
        save_to_memory = self.args.get("save_to_memory", "true").lower() == "true"
        delay = config.get("channel", {}).get("delay_per_video", 3)

        # Find state file
        state_files = list(data_dir.glob("channel_*_state.json"))
        state_path = None
        for sf in state_files:
            try:
                d = json.loads(sf.read_text(encoding="utf-8"))
                if d.get("channel_url") == channel_url:
                    state_path = sf
                    break
            except (json.JSONDecodeError, KeyError):
                continue

        if not state_path:
            return Response(
                message=f"No state file found for {channel_url}. Nothing to retry.",
                break_loop=False,
            )

        state = ChannelState(state_path)
        state.data = json.loads(state_path.read_text(encoding="utf-8"))

        failed = dict(state.data.get("failed", {}))
        if not failed:
            return Response(message="No failed videos to retry.", break_loop=False)

        channel_name = state.data.get("channel_name", "Unknown")
        self.set_progress(f"Retrying {len(failed)} failed videos on {channel_name}...")

        # Clear failed list so they can be re-attempted
        state.data["failed"] = {}
        state.save()

        retried = 0
        still_failed = 0

        for video_id, _old_err in failed.items():
            vid_title = state.title_for(video_id)
            vid_url = f"https://www.youtube.com/watch?v={video_id}"

            self.set_progress(f"Retrying: {vid_title[:50]}...")

            try:
                segments = get_transcript(video_id, vid_url, language)
            except Exception as e:
                state.mark_failed(video_id, str(e))
                still_failed += 1
                continue

            transcript_text = format_transcript(segments, include_timestamps)
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "" for c in vid_title
            )[:80].strip()
            file_path = data_dir / f"transcript_{video_id}_{safe_title}.md"
            file_path.write_text(
                f"# {vid_title}\n\nVideo ID: {video_id}\nChannel: {channel_name}\n\n{transcript_text}",
                encoding="utf-8",
            )

            if save_to_memory:
                timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
                memory_text = (
                    f"YouTube Transcript - {vid_title} "
                    f"(Channel: {channel_name}) [{timestamp}]\n\n{transcript_text}"
                )
                await _save_to_memory(self.agent, memory_text)

            state.mark_done(video_id)
            retried += 1
            await asyncio.sleep(delay)

        lines = [
            f"# Retry Results: {channel_name}",
            f"",
            f"- Recovered: {retried}",
            f"- Still failed: {still_failed}",
            f"- Overall: {state.progress_str}",
            f"",
            f"**State file:** `{state.path}`",
        ]
        return Response(message="\n".join(lines), break_loop=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Create a filesystem-safe slug from text."""
    if not text:
        return "unknown"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in str(text))[:40].strip("_").lower() or "unknown"


async def _save_to_memory(agent, text: str):
    """Save transcript to A0 memory (vector DB with markdown fallback)."""
    try:
        from usr.plugins.memory.helpers.memory import Memory
        db = await Memory.get(agent)
        metadata = {"area": "main", "source": "youtube_channel"}
        await db.insert_text(text, metadata)
    except Exception:
        fallback_dir = (
            Path("/a0/memory/youtube_transcripts")
            if Path("/a0").exists()
            else Path("/git/agent-zero/memory/youtube_transcripts")
        )
        fallback_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        with open(fallback_dir / f"channel_transcript_{ts}.md", "w") as f:
            f.write(text)
