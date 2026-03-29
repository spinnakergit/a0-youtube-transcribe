import os
import time
from pathlib import Path
from helpers.tool import Tool, Response
from usr.plugins.youtube_transcribe.helpers.youtube_client import (
    parse_youtube_url,
    get_video_info,
    get_playlist_videos,
    get_transcript,
    format_transcript,
    format_video_info,
    extract_frames,
    detect_visual_references,
    extract_frames_at_timestamps,
    format_timestamp,
    get_yt_config,
    _data_dir,
)

# Max chars to include in the Response message back to the agent
_RESPONSE_PREVIEW_CHARS = 3000


class YouTubeTranscribe(Tool):
    """Transcribe a YouTube video or playlist with optional visual context extraction."""

    async def execute(self, **kwargs) -> Response:
        url = self.args.get("url", "")
        action = self.args.get("action", "transcribe")

        if not url:
            return Response(
                message="Error: url is required. Provide a YouTube video or playlist URL.",
                break_loop=False,
            )

        config = get_yt_config(self.agent)
        parsed = parse_youtube_url(url)

        if parsed["type"] == "channel":
            return Response(
                message="This looks like a YouTube channel URL. "
                        "Use the **youtube_channel** tool to transcribe all videos from a channel.",
                break_loop=False,
            )

        if parsed["type"] == "unknown":
            return Response(
                message="Error: Could not parse the provided URL as a YouTube video or playlist.",
                break_loop=False,
            )

        if parsed["type"] == "playlist" or (parsed["playlist_id"] and action == "playlist"):
            return await self._transcribe_playlist(url, parsed, config)
        else:
            return await self._transcribe_video(url, parsed, config)

    async def _transcribe_video(self, url: str, parsed: dict, config: dict) -> Response:
        video_id = parsed["video_id"]
        if not video_id:
            return Response(message="Error: Could not extract video ID from URL.", break_loop=False)

        save_to_memory = self.args.get("save_to_memory", "true").lower() == "true"
        extract_visuals = self.args.get("extract_visuals", "").lower()

        # Use config default if not explicitly set
        vis_config = config.get("visual", {})
        if extract_visuals == "":
            extract_visuals = vis_config.get("enabled", True)
        else:
            extract_visuals = extract_visuals == "true"

        language = self.args.get("language", config.get("transcription", {}).get("language", ""))
        include_timestamps = config.get("output", {}).get("include_timestamps", True)

        # Step 1: Get video metadata
        self.set_progress("Fetching video info...")
        try:
            info = get_video_info(url)
        except Exception as e:
            return Response(message=f"Error fetching video info: {e}", break_loop=False)

        video_header = format_video_info(info)
        title = info.get("title", video_id)

        # Step 2: Get transcript
        self.set_progress("Extracting transcript...")
        try:
            segments = get_transcript(video_id, url, language)
        except RuntimeError as e:
            return Response(message=str(e), break_loop=False)

        transcript_text = format_transcript(segments, include_timestamps)

        # Step 3: Visual context extraction
        visual_context = ""
        if extract_visuals:
            self.set_progress("Detecting visual references...")
            visual_refs = detect_visual_references(segments)

            if visual_refs:
                data_dir = _data_dir(config)
                frames_dir = str(data_dir / f"frames_{video_id}")

                # Extract frames at visual reference timestamps
                ref_timestamps = [ref["timestamp"] for ref in visual_refs]
                self.set_progress(f"Extracting {len(ref_timestamps)} frames at visual references...")
                frames = extract_frames_at_timestamps(url, frames_dir, ref_timestamps)

                if frames:
                    # Use LLM to analyze frames for visual context
                    self.set_progress("Analyzing visual content...")
                    visual_context = await self._analyze_frames(frames, visual_refs)
                else:
                    # No frames extracted, still note the visual references
                    visual_lines = ["\n## Visual References Detected"]
                    for ref in visual_refs:
                        ts = format_timestamp(ref["timestamp"])
                        visual_lines.append(f"- [{ts}] Speaker references: \"{ref['keyword']}\" — \"{ref['text'][:100]}\"")
                    visual_context = "\n".join(visual_lines)
            else:
                # Try periodic frame extraction for general context
                interval = vis_config.get("frame_interval", 30)
                max_frames = vis_config.get("max_frames", 20)
                analyze = vis_config.get("analyze_frames", True)

                if analyze and info.get("duration", 0) > 0:
                    data_dir = _data_dir(config)
                    frames_dir = str(data_dir / f"frames_{video_id}")
                    self.set_progress("Extracting periodic frames for context...")
                    frames = extract_frames(url, frames_dir, interval, max_frames)

                    if frames:
                        self.set_progress("Analyzing visual content...")
                        visual_context = await self._analyze_periodic_frames(frames)

        # Step 4: Assemble full output
        output_parts = [
            f"# Transcript: {title}\n",
            video_header,
            f"\n---\n\n## Full Transcript ({len(segments)} segments)\n",
            transcript_text,
        ]
        if visual_context:
            output_parts.append(f"\n---\n{visual_context}")

        full_output = "\n".join(output_parts)

        # Step 5: Save full transcript to file (always — keeps it out of context window)
        data_dir = _data_dir(config)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
        file_name = f"transcript_{video_id}_{safe_title}.md"
        file_path = data_dir / file_name
        file_path.write_text(full_output, encoding="utf-8")

        # Step 6: Save to memory (vector DB)
        if save_to_memory:
            self.set_progress("Saving to memory...")
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
            memory_text = f"YouTube Transcript - {title} [{timestamp}]\n\n{full_output}"
            await _save_to_memory(self.agent, memory_text)

        # Step 7: Return a PREVIEW (not the full transcript) to avoid blowing out context
        preview = transcript_text[:_RESPONSE_PREVIEW_CHARS]
        if len(transcript_text) > _RESPONSE_PREVIEW_CHARS:
            preview += f"\n\n... [truncated — {len(transcript_text):,} chars total]"

        response_parts = [
            f"# Transcript: {title}\n",
            video_header,
            f"\n**Segments:** {len(segments)}",
            f"**Full transcript saved to:** `{file_path}`",
        ]
        if save_to_memory:
            response_parts.append("**Also saved to memory (vector DB)**")
        response_parts.append(f"\n---\n\n## Transcript Preview\n\n{preview}")
        if visual_context:
            # Visual context is usually small enough to include
            vc_preview = visual_context[:2000]
            if len(visual_context) > 2000:
                vc_preview += "\n\n... [visual context truncated]"
            response_parts.append(f"\n---\n{vc_preview}")

        return Response(message="\n".join(response_parts), break_loop=False)

    async def _transcribe_playlist(self, url: str, parsed: dict, config: dict) -> Response:
        max_videos = int(self.args.get("max_videos", config.get("playlist", {}).get("max_videos", 10)))

        self.set_progress("Fetching playlist info...")
        try:
            videos = get_playlist_videos(url, max_videos)
        except Exception as e:
            return Response(message=f"Error fetching playlist: {e}", break_loop=False)

        if not videos:
            return Response(message="No videos found in the playlist.", break_loop=False)

        data_dir = _data_dir(config)
        save_to_memory = self.args.get("save_to_memory", "true").lower() == "true"
        language = self.args.get("language", config.get("transcription", {}).get("language", ""))
        include_timestamps = config.get("output", {}).get("include_timestamps", True)

        full_parts = [f"# Playlist Transcription ({len(videos)} videos)\n"]
        summary_lines = [f"# Playlist Transcription ({len(videos)} videos)\n"]

        for i, video in enumerate(videos):
            vid_id = video.get("id", video.get("url", ""))
            vid_title = video.get("title", f"Video {i+1}")
            vid_url = f"https://www.youtube.com/watch?v={vid_id}"

            self.set_progress(f"Transcribing {i+1}/{len(videos)}: {vid_title[:50]}...")

            try:
                segments = get_transcript(vid_id, vid_url, language)
                transcript_text = format_transcript(segments, include_timestamps)
                full_parts.append(f"\n---\n## {i+1}. {vid_title}\n")
                full_parts.append(f"Video ID: {vid_id}\n")
                full_parts.append(transcript_text)

                # Save individual transcript file
                safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in vid_title)[:80].strip()
                file_path = data_dir / f"transcript_{vid_id}_{safe_title}.md"
                file_path.write_text(
                    f"# {vid_title}\n\nVideo ID: {vid_id}\n\n{transcript_text}",
                    encoding="utf-8",
                )

                summary_lines.append(f"- **{vid_title}** ({len(segments)} segments) → `{file_path}`")
            except Exception as e:
                full_parts.append(f"\n---\n## {i+1}. {vid_title}\n")
                full_parts.append(f"Error: {e}")
                summary_lines.append(f"- **{vid_title}** — Error: {e}")

        full_output = "\n".join(full_parts)

        # Save combined playlist transcript
        playlist_file = data_dir / f"playlist_{parsed.get('playlist_id', 'unknown')}.md"
        playlist_file.write_text(full_output, encoding="utf-8")

        if save_to_memory:
            self.set_progress("Saving to memory...")
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
            memory_text = f"YouTube Playlist Transcript [{timestamp}]\n\n{full_output}"
            await _save_to_memory(self.agent, memory_text)

        summary_lines.append(f"\n**Combined playlist file:** `{playlist_file}`")
        if save_to_memory:
            summary_lines.append("**Also saved to memory (vector DB)**")

        return Response(message="\n".join(summary_lines), break_loop=False)

    async def _analyze_frames(self, frames: list[dict], visual_refs: list[dict]) -> str:
        """Use LLM to analyze frames where visual references were detected."""
        analyses = ["\n## Visual Context Analysis"]

        for i, frame in enumerate(frames):
            ts = format_timestamp(frame["timestamp"])
            ref_text = ""
            # Find matching visual reference
            for ref in visual_refs:
                if abs(ref["timestamp"] - frame["timestamp"]) < 5:
                    ref_text = ref["text"]
                    break

            prompt = (
                f"Analyze this frame from a video at timestamp {ts}. "
                f"The speaker said: \"{ref_text}\"\n\n"
                "Describe what is shown in detail. If there is a chart, graph, table, "
                "or diagram, describe its type, axes, data points, trends, and key takeaways. "
                "If it's a slide, transcribe the text content. "
                "Be specific and detailed about the visual content."
            )

            try:
                frame_path = frame["path"]
                analysis = await self.agent.call_utility_model(
                    system="You are an expert at analyzing visual content from video frames, "
                           "especially charts, graphs, diagrams, and presentation slides.",
                    message=prompt,
                    attachments=[frame_path],
                )
                analyses.append(f"\n### [{ts}] Visual Content\n{analysis}")
            except Exception as e:
                analyses.append(f"\n### [{ts}] Visual Content\nCould not analyze frame: {e}")

        return "\n".join(analyses)

    async def _analyze_periodic_frames(self, frames: list[dict]) -> str:
        """Analyze periodically extracted frames for general visual context."""
        if not frames:
            return ""

        # Only analyze a subset to avoid excessive LLM calls
        step = max(1, len(frames) // 5)
        selected = frames[::step][:5]

        analyses = ["\n## Visual Context (Periodic Frames)"]
        for frame in selected:
            ts = format_timestamp(frame["timestamp"])
            prompt = (
                f"Analyze this frame from a video at timestamp {ts}. "
                "If there is a chart, graph, table, diagram, or presentation slide, "
                "describe it in detail including type, data, and key takeaways. "
                "If it's just a person talking with no visual aids, say 'No visual aids displayed.' "
                "Be concise but thorough for any visual content."
            )
            try:
                analysis = await self.agent.call_utility_model(
                    system="You analyze video frames for visual content.",
                    message=prompt,
                    attachments=[frame["path"]],
                )
                if "no visual aids" not in analysis.lower():
                    analyses.append(f"\n### [{ts}]\n{analysis}")
            except Exception:
                continue

        return "\n".join(analyses) if len(analyses) > 1 else ""


async def _save_to_memory(agent, text: str):
    """Save transcript to A0 memory (vector DB with markdown fallback)."""
    try:
        from plugins.memory.helpers.memory import Memory
        db = await Memory.get(agent)
        metadata = {"area": "main", "source": "youtube_transcribe"}
        await db.insert_text(text, metadata)
    except Exception:
        fallback_dir = (
            Path("/a0/memory/youtube_transcripts")
            if Path("/a0").exists()
            else Path("/git/agent-zero/memory/youtube_transcripts")
        )
        fallback_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        with open(fallback_dir / f"transcript_{ts}.md", "w") as f:
            f.write(text)
