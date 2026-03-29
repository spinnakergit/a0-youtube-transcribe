# Human Test Plan: YouTube Transcriber

> **Plugin:** `youtube_transcribe`
> **Version:** 1.0.0
> **Type:** Utility (no chat bridge, no messaging)
> **Prerequisite:** Plugin deployed and enabled in target container
> **Estimated Time:** 30-40 minutes

---

## How to Use This Plan

1. Work through each phase in order -- phases are gated (Phase 2 requires Phase 1 pass, etc.)
2. For each test, perform the **Action**, check against **Expected**, tell Claude "Pass" or "Fail"
3. Claude will record results in `HUMAN_TEST_RESULTS.md` as you go
4. If any test fails: stop, troubleshoot with Claude, fix, then continue

**Start by telling Claude:** "Start human verification for youtube_transcribe"

---

## Phase 0: Prerequisites & Environment

Before starting, confirm each item:

- [ ] **Container running:** `docker ps | grep a0-verify-active`
- [ ] **WebUI accessible:** Open `http://localhost:50088` in browser
- [ ] **Plugin deployed:** `docker exec a0-verify-active ls /a0/usr/plugins/youtube_transcribe/plugin.yaml`
- [ ] **Plugin enabled:** `docker exec a0-verify-active ls /a0/usr/plugins/youtube_transcribe/.toggle-1`
- [ ] **Symlink exists:** `docker exec a0-verify-active ls -la /a0/plugins/youtube_transcribe`
- [ ] **YouTube accessible:** Container can reach youtube.com (no firewall/proxy blocking)
- [ ] **Test URLs ready:** Have a short public video URL (< 5 min) and a playlist URL ready

**Record your environment:**
```
Container:   a0-verify-active
Port:        50088
Test video:  _______________ (short public video, < 5 min, with captions)
Test playlist: _______________ (small playlist, 3-5 videos)
```

**Suggested test URLs (public, captioned, stable):**
- Short video: `https://www.youtube.com/watch?v=dQw4w9WgXcQ` (3:33, English captions)
- Playlist: Any small public playlist with 3-5 short videos

---

## Phase 1: WebUI Verification (8 tests)

Open the Agent Zero WebUI in your browser.

| ID | Test | Action | Expected | Result |
|----|------|--------|----------|--------|
| HV-01 | Plugin in list | Navigate to Settings > Plugins | "YouTube Transcriber" appears in the plugin list | |
| HV-02 | Toggle works | Toggle the YouTube Transcriber plugin off, then back on | Plugin disables/enables without error or page crash | |
| HV-03 | Dashboard loads | Click the YouTube Transcriber plugin dashboard tab | `main.html` renders with "Dependency Status" panel, 3 tool cards, and Quick Start section | |
| HV-04 | Config loads | Click the YouTube Transcriber plugin settings tab | `config.html` renders with all sections: Transcription, Visual Context Extraction, Output, Playlist | |
| HV-05 | No console errors | Open browser DevTools (F12) > Console tab, reload dashboard and config pages | Zero JavaScript errors in console | |
| HV-06 | Check Status button | On the dashboard, click "Check Status" | Button shows "Checking..." then displays dependency results (green/red dots for yt-dlp, youtube-transcript-api, ffmpeg, Pillow) | |
| HV-07 | Save settings | On config page, change Export Format to "Plain Text", click "Save YouTube Transcriber Settings" | "Saved!" message appears in green next to button | |
| HV-08 | Settings persist | Reload the config page (F5) after saving | Export Format still shows "Plain Text" (value was preserved). Reset to "Markdown" after test | |

---

## Phase 2: Connection & Dependencies (4 tests)

| ID | Test | Action | Expected | Result |
|----|------|--------|----------|--------|
| HV-09 | All deps available | On dashboard, click "Check Status" | All four dependencies show green: yt-dlp, youtube-transcript-api, ffmpeg, Pillow. Message: "All dependencies available." | |
| HV-10 | Core deps sufficient | If ffmpeg or Pillow is missing, check the status message | Status shows "partial" with message: "Core deps OK but optional deps (ffmpeg/Pillow) missing. Frame extraction unavailable." | |
| HV-11 | Missing core dep | Temporarily rename yt-dlp: `docker exec a0-verify-active mv $(which yt-dlp) /tmp/yt-dlp-bak`, click Check Status | Status shows "error" with message: "Core dependencies missing. Run the plugin initializer." Restore after: `docker exec a0-verify-active mv /tmp/yt-dlp-bak $(which yt-dlp 2>/dev/null || echo /usr/local/bin/yt-dlp)` | |
| HV-12 | Post-restart persistence | Run `docker exec a0-verify-active supervisorctl restart run_ui`, wait 15s, reload WebUI | Plugin still listed, dashboard still loads, Check Status still works | |

---

## Phase 3: Core Tools -- youtube_transcribe (5 tests)

Test via the Agent Zero chat interface. Type each prompt into the agent chat.

| ID | Test | Agent Prompt | Expected | Result |
|----|------|-------------|----------|--------|
| HV-13 | Single video transcribe | "Transcribe this YouTube video: `<test_video_url>`" | Agent uses `youtube_transcribe` tool, returns a transcript preview with timestamps, saves full file to `data/` directory | |
| HV-14 | Playlist transcribe | "Transcribe this YouTube playlist: `<test_playlist_url>`" | Agent processes multiple videos (up to max_videos setting), returns summaries/previews for each, files saved to `data/` | |
| HV-15 | Language override | "Transcribe this video in Spanish: `<test_video_url>`" | Agent passes language parameter. If Spanish captions exist, returns Spanish transcript. If not, returns English with note about language availability | |
| HV-16 | Visual context | "Transcribe this video with visual analysis: `<test_video_url>`" | Agent extracts frames (requires ffmpeg + Pillow), transcript includes visual context annotations for detected chart/graph references or periodic frame samples | |
| HV-17 | Invalid URL | "Transcribe this YouTube video: https://youtube.com/watch?v=INVALID_ID_12345" | Agent returns clear error message about video not found or unavailable -- no stack trace, no crash | |

---

## Phase 4: Core Tools -- youtube_summary (3 tests)

| ID | Test | Agent Prompt | Expected | Result |
|----|------|-------------|----------|--------|
| HV-18 | Summarize video | "Summarize this YouTube video: `<test_video_url>`" | Agent uses `youtube_summary` tool, returns structured summary with main topics, key points, data/evidence, and conclusions | |
| HV-19 | Long video handling | "Summarize this YouTube video: https://www.youtube.com/watch?v=<long_video_id>" (use a 30+ min video) | Agent handles long transcript by chunking and synthesizing. Returns coherent summary without token overflow errors | |
| HV-20 | Format check | Review the summary output from HV-18 | Summary is in markdown format (if configured), includes clear section headers, is well-organized and readable | |

---

## Phase 5: Core Tools -- youtube_notes (3 tests)

| ID | Test | Agent Prompt | Expected | Result |
|----|------|-------------|----------|--------|
| HV-21 | Create notes | "Create detailed notes from this video: `<test_video_url>`" | Agent uses `youtube_notes` tool, returns timestamped study notes with key points per section | |
| HV-22 | Section structure | Review notes output from HV-21 | Notes are organized into timed sections (e.g., 0:00-5:00), each with key points, visual references (if any), explanations, and quotes | |
| HV-23 | No transcript available | "Create notes from this video: https://www.youtube.com/watch?v=INVALID_ID_12345" | Agent returns clear error about transcript unavailability -- no crash, graceful handling | |

---

## Phase 6: Security Verification (3 tests)

| ID | Test | Action | Expected | Result |
|----|------|--------|----------|--------|
| HV-24 | CSRF enforcement | Run: `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:50088/api/plugins/youtube_transcribe/youtube_test -H "Content-Type: application/json" -d '{}'` | Returns HTTP 403 Forbidden (CSRF token not provided) | |
| HV-25 | No secrets in responses | Click "Check Status" on dashboard, inspect the JSON response in DevTools Network tab | Response contains only dependency status info (versions, available flags). No tokens, keys, file paths, or internal details leaked | |
| HV-26 | Error handling safe | "Transcribe this video: not-a-url" | Agent returns user-friendly error. No stack traces, internal paths, or sensitive environment details exposed in the response | |

---

## Phase 7: Edge Cases & Error Handling (4 tests)

| ID | Test | Action | Expected | Result |
|----|------|--------|----------|--------|
| HV-27 | Very long video | "Transcribe this YouTube video: `<url_of_2hr+_video>`" | Agent handles gracefully -- either processes with truncation/chunking, or informs user about length. No timeout crash or memory error. Full output saved to file | |
| HV-28 | Private video | "Transcribe this YouTube video: `<url_of_private_video>`" | Agent returns clear error: video is private/unavailable. No crash | |
| HV-29 | Removed/deleted video | "Transcribe this YouTube video: https://www.youtube.com/watch?v=dQw4w9WgXc0" (non-existent variation) | Agent returns clear error about video not found. Graceful handling | |
| HV-30 | Special chars in title | "Transcribe a YouTube video that has special characters in its title (quotes, ampersands, unicode)" | Transcript and file export handle special characters correctly -- no encoding errors, filename sanitized | |

---

## Phase 8: Documentation Spot-Check (3 tests)

| ID | Test | Action | Expected | Result |
|----|------|--------|----------|--------|
| HV-31 | README accuracy | Read README.md, compare listed features to actual behavior tested above | All listed features exist and work: transcribe, summary, notes, visual context, playlist, memory save | |
| HV-32 | Tool count matches | Count tools in `tools/` directory vs README tool table | README lists 3 tools (youtube_transcribe, youtube_summary, youtube_notes) matching the 3 files in `tools/` | |
| HV-33 | Example prompts work | Try 2 example prompts from the README "Quick Start" table | Prompts work as described -- agent uses the correct tool and returns expected output | |

---

## Phase 9: Sign-Off

```
Plugin:           YouTube Transcriber
Version:          1.0.0
Container:        a0-verify-active
Port:             50088
Date:             _______________
Tester:           _______________

Human Tests:      ___/33  PASS  ___/33 FAIL  ___/33 SKIP
Overall:          [ ] APPROVED  [ ] NEEDS WORK  [ ] BLOCKED

Notes:
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________
```

---

## Quick Troubleshooting

| Problem | Check |
|---------|-------|
| "Check Status" fails with fetch error | Is container running? Is port 50088 accessible? Check CSRF -- the endpoint requires it |
| Agent doesn't use YouTube tools | Is plugin enabled (.toggle-1)? Restart run_ui after deploy |
| "No transcript available" | Video may lack captions. Try a different video with known English captions |
| Frame extraction fails | Verify ffmpeg is installed: `docker exec a0-verify-active which ffmpeg` |
| Pillow import error | Run: `docker exec a0-verify-active /opt/venv-a0/bin/pip install Pillow` |
| Token/context overflow | Plugin saves full output to files and returns preview. Check `data/` directory |
| Plugin not loading after restart | Verify symlink: `docker exec a0-verify-active ls -la /a0/plugins/youtube_transcribe` |
| Config changes not taking effect | Use the plugin's own Save button, not the outer framework Save button |
