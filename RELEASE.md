---
status: published
repo: https://github.com/spinnakergit/a0-youtube-transcribe
index_status: in index
published_date: 2026-03-10
version: 1.0.0
---

# Release Status

## Publication
- **GitHub**: https://github.com/spinnakergit/a0-youtube-transcribe
- **Plugin Index**: Already in [agent0ai/a0-plugins](https://github.com/agent0ai/a0-plugins) index
- **Published**: 2026-03-10

## Verification Completed
- **Automated Tests**: No formal regression suite (pre-framework plugin)
- **Human Verification**: Not formally documented (pre-framework)
- **Security Assessment**: Not formally documented (pre-framework)

## Commit History
| Hash | Date | Description |
|------|------|-------------|
| `91b5eee` | 2026-03-10 | Add required name field and migrate to new settings API |
| `20b7493` | 2026-03-08 | Updating with documentation and README |
| `3521a84` | 2026-03-08 | Initial release of YouTube Transcriber plugin for Agent Zero |

## Notes
- YouTube Transcriber was an early plugin built before the AUTOMATED_TEST_FRAMEWORK and HUMAN_VERIFICATION_FRAMEWORK were established.
- Minimal attack surface (read-only transcription, no chat bridge, no external messaging).
- Known issue: `youtube_test.py` has `requires_csrf() = False` — should be reviewed for CSRF compliance.
