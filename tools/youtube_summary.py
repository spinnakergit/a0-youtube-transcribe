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
    get_yt_config,
    _data_dir,
)

# Chars of transcript to send to LLM per chunk (roughly ~3k tokens)
_TRANSCRIPT_LIMIT = 12000

SUMMARY_PROMPT = """You are summarizing a YouTube video. Analyze the following transcript and produce a comprehensive summary.

## Video Info
{video_info}

## Transcript
{transcript}

## Instructions
- Write a clear, well-structured summary of the video content
- Identify the main topics and themes
- Highlight key arguments, claims, or points made
- Note any data, statistics, or evidence presented
- Identify conclusions or recommendations
- If the speaker references visual content (charts, graphs, slides), note what was being discussed
- Keep the summary thorough but concise

## Output Format
### Overview
[2-4 sentence high-level summary]

### Main Topics
1. [Topic]: [Description]
2. [Topic]: [Description]

### Key Points
- [Key point with detail]
- [Key point with detail]

### Data & Evidence
- [Any statistics, data, or evidence cited]

### Conclusions & Takeaways
- [Main conclusions or recommendations]
"""


class YouTubeSummary(Tool):
    """Generate an AI-powered summary of a YouTube video from its transcript."""

    async def execute(self, **kwargs) -> Response:
        url = self.args.get("url", "")
        transcript_text = self.args.get("transcript", "")
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

        if url:
            parsed = parse_youtube_url(url)
            video_id = parsed.get("video_id", "")
            if not video_id:
                return Response(
                    message="Error: Could not extract video ID from URL.",
                    break_loop=False,
                )

            # Get metadata
            self.set_progress("Fetching video info...")
            try:
                info = get_video_info(url)
                video_info_str = format_video_info(info)
                title = info.get("title", video_id)
            except Exception:
                video_info_str = f"Video URL: {url}"

            # Get transcript if not provided
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

        # For long transcripts, summarize in chunks then combine
        if len(transcript_text) > _TRANSCRIPT_LIMIT:
            summary = await self._chunked_summary(transcript_text, video_info_str)
        else:
            self.set_progress("Generating summary...")
            prompt = SUMMARY_PROMPT.format(
                video_info=video_info_str or "Not available",
                transcript=transcript_text,
            )
            try:
                summary = await self.agent.call_utility_model(
                    system="You are an expert at summarizing video content. "
                           "Produce clear, well-organized summaries that capture the essential information.",
                    message=prompt,
                )
            except Exception as e:
                return Response(message=f"Error generating summary: {e}", break_loop=False)

        output = f"# Summary: {title}\n\n{video_info_str}\n\n---\n\n{summary}"

        # Save full summary to file
        data_dir = _data_dir(config)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
        file_name = f"summary_{video_id}_{safe_title}.md" if video_id else f"summary_{safe_title}.md"
        file_path = data_dir / file_name
        file_path.write_text(output, encoding="utf-8")

        # Save to memory
        if save_to_memory:
            self.set_progress("Saving to memory...")
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
            memory_text = f"YouTube Summary - {title} [{timestamp}]\n\n{output}"
            await _save_to_memory(self.agent, memory_text)

        # Cap response size to avoid context blowout
        if len(output) > 6000:
            response_text = output[:6000] + f"\n\n... [truncated — full summary at `{file_path}`]"
        else:
            response_text = output + f"\n\n**Full summary saved to:** `{file_path}`"

        if save_to_memory:
            response_text += "\n[Also saved to memory]"

        return Response(message=response_text, break_loop=False)

    async def _chunked_summary(self, transcript: str, video_info: str) -> str:
        """Summarize a long transcript by breaking into chunks then synthesizing."""
        chunks = []
        for i in range(0, len(transcript), _TRANSCRIPT_LIMIT):
            chunks.append(transcript[i:i + _TRANSCRIPT_LIMIT])

        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            self.set_progress(f"Summarizing chunk {i+1}/{len(chunks)}...")
            prompt = (
                f"Summarize this portion (part {i+1} of {len(chunks)}) of a video transcript. "
                f"Capture all key points, data, and arguments.\n\n"
                f"## Video Info\n{video_info}\n\n"
                f"## Transcript (Part {i+1})\n{chunk}"
            )
            try:
                chunk_summary = await self.agent.call_utility_model(
                    system="You summarize video transcript sections concisely but thoroughly.",
                    message=prompt,
                )
                chunk_summaries.append(f"### Part {i+1}\n{chunk_summary}")
            except Exception as e:
                chunk_summaries.append(f"### Part {i+1}\nError: {e}")

        combined = "\n\n".join(chunk_summaries)

        # Synthesize if combined is small enough
        if len(combined) < _TRANSCRIPT_LIMIT:
            self.set_progress("Synthesizing final summary...")
            prompt = (
                "Combine these section summaries into one cohesive, well-structured summary.\n\n"
                f"## Video Info\n{video_info}\n\n"
                f"## Section Summaries\n{combined}\n\n"
                "Produce a unified summary with: Overview, Main Topics, Key Points, "
                "Data & Evidence, and Conclusions & Takeaways."
            )
            try:
                return await self.agent.call_utility_model(
                    system="You synthesize multiple summaries into one cohesive overview.",
                    message=prompt,
                )
            except Exception:
                pass

        return combined


async def _save_to_memory(agent, text: str):
    """Save summary to A0 memory."""
    try:
        from plugins.memory.helpers.memory import Memory
        db = await Memory.get(agent)
        metadata = {"area": "main", "source": "youtube_summary"}
        await db.insert_text(text, metadata)
    except Exception:
        fallback_dir = (
            Path("/a0/memory/youtube_summaries")
            if Path("/a0").exists()
            else Path("/git/agent-zero/memory/youtube_summaries")
        )
        fallback_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        with open(fallback_dir / f"summary_{ts}.md", "w") as f:
            f.write(text)
