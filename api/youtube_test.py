"""API endpoint: Test YouTube Transcriber dependencies.
URL: POST /api/plugins/youtube_transcribe/youtube_test
"""
import shutil
import subprocess
from helpers.api import ApiHandler, Request, Response


class YouTubeTest(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        checks = {}

        # Check yt-dlp
        try:
            r = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
            checks["yt_dlp"] = {
                "available": r.returncode == 0,
                "version": r.stdout.strip() if r.returncode == 0 else None,
            }
        except Exception as e:
            checks["yt_dlp"] = {"available": False, "error": str(e)}

        # Check youtube-transcript-api
        try:
            r = subprocess.run(
                ["/opt/venv-a0/bin/python", "-c",
                 "import youtube_transcript_api; print('installed')"],
                capture_output=True, text=True, timeout=10,
            )
            checks["youtube_transcript_api"] = {
                "available": r.returncode == 0,
                "version": r.stdout.strip() if r.returncode == 0 else None,
            }
        except Exception as e:
            checks["youtube_transcript_api"] = {"available": False, "error": str(e)}

        # Check ffmpeg
        try:
            r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
            version_line = r.stdout.split("\n")[0] if r.stdout else ""
            checks["ffmpeg"] = {
                "available": r.returncode == 0,
                "version": version_line,
            }
        except Exception as e:
            checks["ffmpeg"] = {"available": False, "error": str(e)}

        # Check Pillow
        try:
            r = subprocess.run(
                ["/opt/venv-a0/bin/python", "-c", "import PIL; print(PIL.__version__)"],
                capture_output=True, text=True, timeout=10,
            )
            checks["pillow"] = {
                "available": r.returncode == 0,
                "version": r.stdout.strip() if r.returncode == 0 else None,
            }
        except Exception as e:
            checks["pillow"] = {"available": False, "error": str(e)}

        # Overall status
        all_ok = all(c.get("available", False) for c in checks.values())
        core_ok = (
            checks.get("yt_dlp", {}).get("available", False)
            and checks.get("youtube_transcript_api", {}).get("available", False)
        )

        status = "ok" if all_ok else ("partial" if core_ok else "error")
        if not core_ok:
            message = "Core dependencies missing. Run the plugin initializer."
        elif not all_ok:
            message = "Core deps OK but optional deps (ffmpeg/Pillow) missing. Frame extraction unavailable."
        else:
            message = "All dependencies available."

        return {"status": status, "checks": checks, "message": message}
