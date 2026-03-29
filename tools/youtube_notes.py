import time
from pathlib import Path
from helpers.tool import Tool, Response
from usr.plugins.youtube_transcribe.helpers.youtube_client import (
    parse_youtube_url,
    get_video_info,
    get_transcript,
    format_transcript,
    format_video_info,
    format_timestamp,
    group_segments_by_interval,
    detect_visual_references,
    get_yt_config,
    _data_dir,
)

# Max chars of section text to send to LLM
_SECTION_TEXT_LIMIT = 8000
# Max chars to return in the Response message
_RESPONSE_LIMIT = 6000

NOTES_PROMPT = """You are creating detailed study notes from a section of a YouTube video transcript.

## Video Info
{video_info}

## Section: {section_label}
{section_text}

## Visual References in This Section
{visual_refs}

## Instructions
- Create detailed, structured notes for this section of the video
- Capture all important points, explanations, and details
- If the speaker references charts, graphs, or visuals, describe what they are discussing in detail
  and add contextual notes about what the visual likely shows based on the speaker's description
- Include relevant quotes for key statements
- Note any technical terms and their explanations
- Organize with clear headings and bullet points
- Make the notes useful as standalone study material

## Output Format
### [Section Topic Title]
**Time Range:** {time_range}

#### Key Points
- [Detailed point]
- [Detailed point]

#### Visual Content Referenced
- [Description of any charts/graphs/slides discussed, with context about what they show]

#### Details & Explanations
- [Detailed explanations, examples, data mentioned]

#### Notable Quotes
- "[Exact or near-exact quote]" — regarding [context]
"""


class YouTubeNotes(Tool):
    """Generate detailed, timestamped study notes from a YouTube video."""

    async def execute(self, **kwargs) -> Response:
        url = self.args.get("url", "")
        transcript_text = self.args.get("transcript", "")
        section_minutes = int(self.args.get("section_minutes", "5"))
        save_to_memory = self.args.get("save_to_memory", "true").lower() == "true"

        if not url and not transcript_text:
            return Response(
                message="Error: Provide either a 'url' (YouTube video URL) or 'transcript' (pre-extracted text).",
                break_loop=False,
            )

        config = get_yt_config(self.agent)
        video_info_str = ""
        title = "YouTube Video"
        video_id = ""
        segments = []

        if url:
            parsed = parse_youtube_url(url)
            video_id = parsed.get("video_id", "")
            if not video_id:
                return Response(
                    message="Error: Could not extract video ID from URL.",
                    break_loop=False,
                )

            self.set_progress("Fetching video info...")
            try:
                info = get_video_info(url)
                video_info_str = format_video_info(info)
                title = info.get("title", video_id)
            except Exception:
                video_info_str = f"Video URL: {url}"

            if not transcript_text:
                self.set_progress("Extracting transcript...")
                language = self.args.get(
                    "language",
                    config.get("transcription", {}).get("language", ""),
                )
                try:
                    segments = get_transcript(video_id, url, language)
                    transcript_text = format_transcript(segments, include_timestamps=True)
                except RuntimeError as e:
                    return Response(message=str(e), break_loop=False)

        # If we have raw transcript text but no segments, generate notes from text
        if not segments and transcript_text:
            return await self._notes_from_text(
                transcript_text, video_info_str, title, video_id, save_to_memory, config
            )

        # Detect visual references across all segments
        visual_refs = detect_visual_references(segments)

        # Group segments into sections
        section_seconds = section_minutes * 60
        sections = group_segments_by_interval(segments, section_seconds)

        if not sections:
            return Response(message="No transcript content to generate notes from.", break_loop=False)

        output_parts = [f"# Detailed Notes: {title}\n", video_info_str, "\n---\n"]

        for i, section in enumerate(sections):
            start_ts = format_timestamp(section["start"])
            end_ts = format_timestamp(section["end"])
            time_range = f"{start_ts} - {end_ts}"
            section_label = f"Section {i+1} ({time_range})"

            self.set_progress(f"Generating notes for {section_label}...")

            # Find visual references within this section's time range
            section_visuals = [
                ref for ref in visual_refs
                if section["start"] <= ref["timestamp"] < section["end"]
            ]
            visual_text = "None detected"
            if section_visuals:
                visual_lines = []
                for ref in section_visuals:
                    ts = format_timestamp(ref["timestamp"])
                    visual_lines.append(f"- [{ts}] \"{ref['keyword']}\" — \"{ref['text'][:150]}\"")
                visual_text = "\n".join(visual_lines)

            prompt = NOTES_PROMPT.format(
                video_info=video_info_str or "Not available",
                section_label=section_label,
                section_text=section["text"][:_SECTION_TEXT_LIMIT],
                visual_refs=visual_text,
                time_range=time_range,
            )

            try:
                notes = await self.agent.call_utility_model(
                    system="You are an expert note-taker creating detailed study notes from video content. "
                           "Pay special attention to visual references — when a speaker mentions a chart, "
                           "graph, or slide, provide detailed contextual notes about what the visual likely shows.",
                    message=prompt,
                )
                output_parts.append(f"\n{notes}")
            except Exception as e:
                output_parts.append(f"\n### Section {i+1} ({time_range})\nError generating notes: {e}")

        full_output = "\n".join(output_parts)

        # Save to file
        data_dir = _data_dir(config)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
        file_name = f"notes_{video_id}_{safe_title}.md" if video_id else f"notes_{safe_title}.md"
        file_path = data_dir / file_name
        file_path.write_text(full_output, encoding="utf-8")

        # Save to memory
        if save_to_memory:
            self.set_progress("Saving to memory...")
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
            memory_text = f"YouTube Notes - {title} [{timestamp}]\n\n{full_output}"
            await _save_to_memory(self.agent, memory_text)

        # Return capped response
        if len(full_output) > _RESPONSE_LIMIT:
            response_text = full_output[:_RESPONSE_LIMIT]
            response_text += (
                f"\n\n... [truncated — {len(sections)} sections total]\n"
                f"**Full notes saved to:** `{file_path}`"
            )
        else:
            response_text = full_output + f"\n\n**Full notes saved to:** `{file_path}`"

        if save_to_memory:
            response_text += "\n[Also saved to memory]"

        return Response(message=response_text, break_loop=False)

    async def _notes_from_text(
        self, transcript: str, video_info: str, title: str,
        video_id: str, save_to_memory: bool, config: dict,
    ) -> Response:
        """Generate notes from raw transcript text (no timestamp segments available)."""
        self.set_progress("Generating notes from text...")

        # Limit transcript sent to LLM
        limited = transcript[:_SECTION_TEXT_LIMIT]
        prompt = (
            "Create detailed, structured study notes from this video transcript.\n\n"
            f"## Video Info\n{video_info}\n\n"
            f"## Transcript\n{limited}\n\n"
            "Include: key points, visual content references, detailed explanations, "
            "notable quotes, and organize with clear section headings."
        )

        try:
            notes = await self.agent.call_utility_model(
                system="You are an expert note-taker creating detailed study notes from video content.",
                message=prompt,
            )
        except Exception as e:
            return Response(message=f"Error generating notes: {e}", break_loop=False)

        output = f"# Detailed Notes: {title}\n\n{video_info}\n\n---\n\n{notes}"

        # Save to file
        data_dir = _data_dir(config)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
        file_name = f"notes_{video_id}_{safe_title}.md" if video_id else f"notes_{safe_title}.md"
        file_path = data_dir / file_name
        file_path.write_text(output, encoding="utf-8")

        if save_to_memory:
            self.set_progress("Saving to memory...")
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
            memory_text = f"YouTube Notes - {title} [{timestamp}]\n\n{output}"
            await _save_to_memory(self.agent, memory_text)

        if len(output) > _RESPONSE_LIMIT:
            response_text = output[:_RESPONSE_LIMIT] + f"\n\n... [truncated]\n**Full notes at:** `{file_path}`"
        else:
            response_text = output + f"\n\n**Full notes saved to:** `{file_path}`"

        if save_to_memory:
            response_text += "\n[Also saved to memory]"

        return Response(message=response_text, break_loop=False)


async def _save_to_memory(agent, text: str):
    """Save notes to A0 memory."""
    try:
        from plugins.memory.helpers.memory import Memory
        db = await Memory.get(agent)
        metadata = {"area": "main", "source": "youtube_notes"}
        await db.insert_text(text, metadata)
    except Exception:
        fallback_dir = (
            Path("/a0/memory/youtube_notes")
            if Path("/a0").exists()
            else Path("/git/agent-zero/memory/youtube_notes")
        )
        fallback_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        with open(fallback_dir / f"notes_{ts}.md", "w") as f:
            f.write(text)
