#!/bin/bash
# YouTube Transcriber Plugin Regression Test Suite
# Runs against a live Agent Zero container with the youtube_transcribe plugin installed.
#
# Usage:
#   ./regression_test.sh                    # Test against default (agent-zero-dev-latest on port 50084)
#   ./regression_test.sh <container> <port> # Test against specific container
#
# Requires: curl, python3 (for JSON parsing)

CONTAINER="${1:-agent-zero-dev-latest}"
PORT="${2:-50084}"
BASE_URL="http://localhost:${PORT}"

PASSED=0
FAILED=0
SKIPPED=0
ERRORS=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

pass() {
    PASSED=$((PASSED + 1))
    echo -e "  ${GREEN}PASS${NC} $1"
}

fail() {
    FAILED=$((FAILED + 1))
    ERRORS="${ERRORS}\n  - $1: $2"
    echo -e "  ${RED}FAIL${NC} $1 — $2"
}

skip() {
    SKIPPED=$((SKIPPED + 1))
    echo -e "  ${YELLOW}SKIP${NC} $1 — $2"
}

section() {
    echo ""
    echo -e "${CYAN}━━━ $1 ━━━${NC}"
}

# Helper: acquire CSRF token + session cookie from the container
CSRF_TOKEN=""
setup_csrf() {
    if [ -z "$CSRF_TOKEN" ]; then
        CSRF_TOKEN=$(docker exec "$CONTAINER" bash -c '
            curl -s -c /tmp/test_cookies.txt \
                -H "Origin: http://localhost" \
                "http://localhost/api/csrf_token" 2>/dev/null
        ' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
    fi
}

# Helper: curl the container's internal API (with CSRF token)
api() {
    local endpoint="$1"
    local data="${2:-}"
    setup_csrf
    if [ -n "$data" ]; then
        docker exec "$CONTAINER" curl -s -X POST "http://localhost/api/plugins/youtube_transcribe/${endpoint}" \
            -H "Content-Type: application/json" \
            -H "Origin: http://localhost" \
            -H "X-CSRF-Token: ${CSRF_TOKEN}" \
            -b /tmp/test_cookies.txt \
            -d "$data" 2>/dev/null
    else
        docker exec "$CONTAINER" curl -s "http://localhost/api/plugins/youtube_transcribe/${endpoint}" \
            -H "Origin: http://localhost" \
            -H "X-CSRF-Token: ${CSRF_TOKEN}" \
            -b /tmp/test_cookies.txt 2>/dev/null
    fi
}

# Helper: run Python inside the container
container_python() {
    echo "$1" | docker exec -i "$CONTAINER" bash -c 'cd /a0 && PYTHONPATH=/a0 /opt/venv-a0/bin/python3 -' 2>&1
}

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   YouTube Transcriber Plugin Regression Test Suite  ║${NC}"
echo -e "${CYAN}║   Container: ${CONTAINER}${NC}"
echo -e "${CYAN}║   Port: ${PORT}${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"

# ============================================================
section "1. Container & Service Health"
# ============================================================

# T1.1: Container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    pass "T1.1 Container is running"
else
    fail "T1.1 Container is running" "Container '${CONTAINER}' not found"
    echo -e "\n${RED}Cannot proceed without a running container.${NC}"
    exit 1
fi

# T1.2: Agent Zero HTTP service is responsive
HTTP_STATUS=$(docker exec "$CONTAINER" curl -s -o /dev/null -w "%{http_code}" "http://localhost/" 2>/dev/null)
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "302" ]; then
    pass "T1.2 HTTP service is responsive (status: $HTTP_STATUS)"
else
    fail "T1.2 HTTP service is responsive" "Got status $HTTP_STATUS"
fi

# T1.3: Python venv is available
PYTHON_OK=$(docker exec "$CONTAINER" /opt/venv-a0/bin/python3 -c "print('ok')" 2>/dev/null)
if [ "$PYTHON_OK" = "ok" ]; then
    pass "T1.3 Python venv is available"
else
    fail "T1.3 Python venv is available" "Cannot run Python in venv"
fi

# ============================================================
section "2. Plugin Installation Verification"
# ============================================================

# T2.1: Plugin directory exists
if docker exec "$CONTAINER" test -d /a0/usr/plugins/youtube_transcribe; then
    pass "T2.1 Plugin directory exists"
else
    fail "T2.1 Plugin directory exists" "/a0/usr/plugins/youtube_transcribe not found"
fi

# T2.2: Symlink exists
if docker exec "$CONTAINER" test -L /a0/plugins/youtube_transcribe || docker exec "$CONTAINER" test -d /a0/plugins/youtube_transcribe; then
    pass "T2.2 Plugin symlink exists"
else
    fail "T2.2 Plugin symlink exists" "/a0/plugins/youtube_transcribe not found"
fi

# T2.3: Toggle file
if docker exec "$CONTAINER" test -f /a0/usr/plugins/youtube_transcribe/.toggle-1; then
    pass "T2.3 Plugin enabled (.toggle-1)"
else
    fail "T2.3 Plugin enabled" ".toggle-1 not found"
fi

# T2.4: plugin.yaml exists and has correct name
YAML_NAME=$(docker exec "$CONTAINER" cat /a0/usr/plugins/youtube_transcribe/plugin.yaml 2>/dev/null | python3 -c "import sys,yaml; print(yaml.safe_load(sys.stdin).get('name',''))" 2>/dev/null)
if [ "$YAML_NAME" = "youtube_transcribe" ]; then
    pass "T2.4 plugin.yaml name=youtube_transcribe"
else
    fail "T2.4 plugin.yaml name" "Expected 'youtube_transcribe', got '$YAML_NAME'"
fi

# T2.5: default_config.yaml exists
if docker exec "$CONTAINER" test -f /a0/usr/plugins/youtube_transcribe/default_config.yaml; then
    pass "T2.5 default_config.yaml exists"
else
    fail "T2.5 default_config.yaml exists" "File not found"
fi

# T2.6: yt-dlp is installed
YTDLP_OK=$(docker exec "$CONTAINER" bash -c 'yt-dlp --version' 2>/dev/null)
if [ -n "$YTDLP_OK" ]; then
    pass "T2.6 yt-dlp installed (version: $YTDLP_OK)"
else
    fail "T2.6 yt-dlp installed" "yt-dlp not found"
fi

# T2.7: youtube-transcript-api is installed
YTAPI_OK=$(docker exec "$CONTAINER" /opt/venv-a0/bin/python3 -c "import youtube_transcript_api; print('ok')" 2>/dev/null)
if echo "$YTAPI_OK" | grep -q "ok"; then
    pass "T2.7 youtube-transcript-api installed"
else
    fail "T2.7 youtube-transcript-api installed" "Import failed"
fi

# T2.8: Pillow is installed
PIL_OK=$(docker exec "$CONTAINER" /opt/venv-a0/bin/python3 -c "import PIL; print(PIL.__version__)" 2>/dev/null)
if [ -n "$PIL_OK" ]; then
    pass "T2.8 Pillow installed (version: $PIL_OK)"
else
    skip "T2.8 Pillow installed" "Optional dependency not available"
fi

# ============================================================
section "3. Python Imports"
# ============================================================

# T3.1: youtube_client helper module
RESULT=$(container_python "from usr.plugins.youtube_transcribe.helpers.youtube_client import parse_youtube_url, get_yt_config, format_timestamp; print('ok')")
if echo "$RESULT" | grep -q "ok"; then
    pass "T3.1 import youtube_client helper"
else
    fail "T3.1 import youtube_client helper" "$RESULT"
fi

# T3.2: helpers __init__.py
RESULT=$(container_python "import usr.plugins.youtube_transcribe.helpers; print('ok')")
if echo "$RESULT" | grep -q "ok"; then
    pass "T3.2 import helpers package"
else
    fail "T3.2 import helpers package" "$RESULT"
fi

# T3.3: Tool class imports
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.tools.youtube_transcribe import YouTubeTranscribe
from usr.plugins.youtube_transcribe.tools.youtube_summary import YouTubeSummary
from usr.plugins.youtube_transcribe.tools.youtube_notes import YouTubeNotes
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T3.3 import all Tool classes"
else
    fail "T3.3 import Tool classes" "$RESULT"
fi

# ============================================================
section "4. API Endpoints"
# ============================================================

# T4.1: CSRF rejection (no token) — request without CSRF must be blocked
RESULT=$(docker exec "$CONTAINER" curl -s -X POST "http://localhost/api/plugins/youtube_transcribe/youtube_test" \
    -H "Content-Type: application/json" \
    -d '{}' 2>/dev/null)
STATUS=$(echo "$RESULT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('error',''))
except:
    print('blocked')
" 2>/dev/null)
if [ -n "$STATUS" ]; then
    pass "T4.1 CSRF rejection (no token)"
else
    fail "T4.1 CSRF rejection" "Request was not rejected"
fi

# T4.2: Test endpoint GET (with CSRF)
RESULT=$(api "youtube_test")
EP_STATUS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
if [ -n "$EP_STATUS" ]; then
    pass "T4.2 Test endpoint GET responds (status: $EP_STATUS)"
else
    fail "T4.2 Test endpoint GET" "Unexpected response: $RESULT"
fi

# T4.3: Test endpoint POST (with CSRF)
RESULT=$(api "youtube_test" '{}')
EP_STATUS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
if [ -n "$EP_STATUS" ]; then
    pass "T4.3 Test endpoint POST responds (status: $EP_STATUS)"
else
    fail "T4.3 Test endpoint POST" "Unexpected response: $RESULT"
fi

# T4.4: Test endpoint returns dependency checks
RESULT=$(api "youtube_test" '{}')
HAS_CHECKS=$(echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
checks = d.get('checks', {})
has_ytdlp = 'yt_dlp' in checks
has_ytapi = 'youtube_transcript_api' in checks
has_ffmpeg = 'ffmpeg' in checks
has_pillow = 'pillow' in checks
print('OK' if (has_ytdlp and has_ytapi and has_ffmpeg and has_pillow) else 'MISSING')
" 2>/dev/null)
if [ "$HAS_CHECKS" = "OK" ]; then
    pass "T4.4 Test endpoint returns all dependency checks"
else
    fail "T4.4 Dependency check response" "Expected yt_dlp, youtube_transcript_api, ffmpeg, pillow checks"
fi

# T4.5: Test endpoint returns message field
RESULT=$(api "youtube_test" '{}')
HAS_MSG=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('message') else 'MISSING')" 2>/dev/null)
if [ "$HAS_MSG" = "OK" ]; then
    pass "T4.5 Test endpoint returns message field"
else
    fail "T4.5 Test endpoint message" "No message field in response"
fi

# ============================================================
section "6. Tool Class Loading"
# ============================================================

# T6.1: YouTubeTranscribe tool
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.tools.youtube_transcribe import YouTubeTranscribe
from helpers.tool import Tool
assert issubclass(YouTubeTranscribe, Tool), 'Not a Tool subclass'
assert hasattr(YouTubeTranscribe, 'execute'), 'No execute method'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T6.1 YouTubeTranscribe is a valid Tool subclass"
else
    fail "T6.1 YouTubeTranscribe" "$RESULT"
fi

# T6.2: YouTubeSummary tool
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.tools.youtube_summary import YouTubeSummary
from helpers.tool import Tool
assert issubclass(YouTubeSummary, Tool), 'Not a Tool subclass'
assert hasattr(YouTubeSummary, 'execute'), 'No execute method'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T6.2 YouTubeSummary is a valid Tool subclass"
else
    fail "T6.2 YouTubeSummary" "$RESULT"
fi

# T6.3: YouTubeNotes tool
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.tools.youtube_notes import YouTubeNotes
from helpers.tool import Tool
assert issubclass(YouTubeNotes, Tool), 'Not a Tool subclass'
assert hasattr(YouTubeNotes, 'execute'), 'No execute method'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T6.3 YouTubeNotes is a valid Tool subclass"
else
    fail "T6.3 YouTubeNotes" "$RESULT"
fi

# ============================================================
section "7. Prompt Files"
# ============================================================

PROMPT_TOOLS=("youtube_transcribe" "youtube_summary" "youtube_notes")

for tool in "${PROMPT_TOOLS[@]}"; do
    PROMPT_FILE="/a0/usr/plugins/youtube_transcribe/prompts/agent.system.tool.${tool}.md"
    if docker exec "$CONTAINER" test -f "$PROMPT_FILE"; then
        SIZE=$(docker exec "$CONTAINER" wc -c < "$PROMPT_FILE" 2>/dev/null)
        if [ "$SIZE" -ge 50 ]; then
            pass "T7 Prompt: ${tool}.md (${SIZE} bytes)"
        else
            fail "T7 Prompt: ${tool}.md" "Too small (${SIZE} bytes)"
        fi
    else
        fail "T7 Prompt: ${tool}.md" "File not found"
    fi
done

# ============================================================
section "8. Skills"
# ============================================================

# T8.1: youtube-transcribe skill
if docker exec "$CONTAINER" test -f /a0/usr/skills/youtube-transcribe/SKILL.md; then
    SIZE=$(docker exec "$CONTAINER" wc -c < /a0/usr/skills/youtube-transcribe/SKILL.md 2>/dev/null)
    pass "T8.1 Skill: youtube-transcribe (${SIZE} bytes)"
else
    # Skills may live under plugin dir or usr/skills
    if docker exec "$CONTAINER" test -f /a0/usr/plugins/youtube_transcribe/skills/youtube-transcribe/SKILL.md; then
        SIZE=$(docker exec "$CONTAINER" wc -c < /a0/usr/plugins/youtube_transcribe/skills/youtube-transcribe/SKILL.md 2>/dev/null)
        pass "T8.1 Skill: youtube-transcribe (${SIZE} bytes, in plugin dir)"
    else
        fail "T8.1 Skill: youtube-transcribe" "SKILL.md not found"
    fi
fi

# T8.2: youtube-research skill
if docker exec "$CONTAINER" test -f /a0/usr/skills/youtube-research/SKILL.md; then
    SIZE=$(docker exec "$CONTAINER" wc -c < /a0/usr/skills/youtube-research/SKILL.md 2>/dev/null)
    pass "T8.2 Skill: youtube-research (${SIZE} bytes)"
else
    if docker exec "$CONTAINER" test -f /a0/usr/plugins/youtube_transcribe/skills/youtube-research/SKILL.md; then
        SIZE=$(docker exec "$CONTAINER" wc -c < /a0/usr/plugins/youtube_transcribe/skills/youtube-research/SKILL.md 2>/dev/null)
        pass "T8.2 Skill: youtube-research (${SIZE} bytes, in plugin dir)"
    else
        fail "T8.2 Skill: youtube-research" "SKILL.md not found"
    fi
fi

# ============================================================
section "9. WebUI Files"
# ============================================================

# T9.1: main.html exists
if docker exec "$CONTAINER" test -f /a0/usr/plugins/youtube_transcribe/webui/main.html; then
    pass "T9.1 webui/main.html exists"
else
    fail "T9.1 webui/main.html" "File not found"
fi

# T9.2: config.html exists
if docker exec "$CONTAINER" test -f /a0/usr/plugins/youtube_transcribe/webui/config.html; then
    pass "T9.2 webui/config.html exists"
else
    fail "T9.2 webui/config.html" "File not found"
fi

# T9.3: data-yt attributes used (not bare IDs for scoping)
DATA_ATTRS_MAIN=$(docker exec "$CONTAINER" grep -c 'data-yt=' /a0/usr/plugins/youtube_transcribe/webui/main.html 2>/dev/null)
DATA_ATTRS_CFG=$(docker exec "$CONTAINER" grep -c 'data-yt=' /a0/usr/plugins/youtube_transcribe/webui/config.html 2>/dev/null)
TOTAL_ATTRS=$((DATA_ATTRS_MAIN + DATA_ATTRS_CFG))
if [ "$TOTAL_ATTRS" -ge 5 ]; then
    pass "T9.3 WebUI uses data-yt attributes (main: $DATA_ATTRS_MAIN, config: $DATA_ATTRS_CFG)"
else
    fail "T9.3 data-yt attributes" "Expected >= 5 total, got $TOTAL_ATTRS"
fi

# T9.4: fetchApi or fetch pattern in WebUI JS
# Note: YouTube Transcriber is a utility plugin; main.html uses fetch() for the test endpoint.
# The standard is globalThis.fetchApi || fetch for CSRF-aware calls.
FETCH_MAIN=$(docker exec "$CONTAINER" grep -c 'fetchApi\|globalThis.fetchApi\|fetch(' /a0/usr/plugins/youtube_transcribe/webui/main.html 2>/dev/null)
FETCH_CFG=$(docker exec "$CONTAINER" grep -c 'fetchApi\|globalThis.fetchApi\|fetch(' /a0/usr/plugins/youtube_transcribe/webui/config.html 2>/dev/null)
TOTAL_FETCH=$((FETCH_MAIN + FETCH_CFG))
if [ "$TOTAL_FETCH" -ge 1 ]; then
    pass "T9.4 WebUI has fetch/fetchApi calls ($TOTAL_FETCH refs)"
else
    fail "T9.4 fetch/fetchApi usage" "Not found"
fi

# ============================================================
section "10. Framework Compatibility"
# ============================================================

# T10.1: get_plugin_config works
RESULT=$(container_python "
from helpers import plugins
config = plugins.get_plugin_config('youtube_transcribe')
print('OK' if isinstance(config, dict) else 'FAIL')
")
if echo "$RESULT" | grep -q "OK"; then
    pass "T10.1 get_plugin_config('youtube_transcribe') works"
else
    fail "T10.1 get_plugin_config" "$RESULT"
fi

# T10.2: Plugin coexists with other plugins (infection_check coexistence)
RESULT=$(container_python "
import os
plugins_dir = '/a0/plugins' if os.path.exists('/a0/plugins') else '/a0/usr/plugins'
found = [d for d in os.listdir(plugins_dir) if os.path.isdir(os.path.join(plugins_dir, d)) and not d.startswith('.')]
has_yt = 'youtube_transcribe' in found
print(f'OK:{len(found)}' if has_yt else 'MISSING')
")
if echo "$RESULT" | grep -q "OK"; then
    PLUGIN_COUNT=$(echo "$RESULT" | grep -oP 'OK:\K\d+')
    pass "T10.2 Coexists with other plugins (${PLUGIN_COUNT} total)"
else
    fail "T10.2 Plugin coexistence" "$RESULT"
fi

# T10.3: No hook filename conflicts (hook prefixes)
RESULT=$(container_python "
import os, glob
hook_dirs = glob.glob('/a0/usr/plugins/*/extensions/python/agent_init/')
all_names = []
for hd in hook_dirs:
    for f in glob.glob(hd + '*.py'):
        all_names.append(os.path.basename(f))
dupes = [n for n in set(all_names) if all_names.count(n) > 1]
print('OK' if not dupes else f'CONFLICT:{dupes}')
")
if echo "$RESULT" | grep -q "OK"; then
    pass "T10.3 No hook filename conflicts"
else
    fail "T10.3 Hook conflicts" "$RESULT"
fi

# ============================================================
section "11. YouTube-Specific Logic"
# ============================================================

# T11.1: parse_youtube_url — standard video
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import parse_youtube_url
r = parse_youtube_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
assert r['type'] == 'video', f'type: {r[\"type\"]}'
assert r['video_id'] == 'dQw4w9WgXcQ', f'id: {r[\"video_id\"]}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.1 parse_youtube_url: standard video"
else
    fail "T11.1 parse_youtube_url video" "$RESULT"
fi

# T11.2: parse_youtube_url — playlist
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import parse_youtube_url
r = parse_youtube_url('https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf')
assert r['type'] == 'playlist', f'type: {r[\"type\"]}'
assert r['playlist_id'] == 'PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf', f'pl: {r[\"playlist_id\"]}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.2 parse_youtube_url: playlist"
else
    fail "T11.2 parse_youtube_url playlist" "$RESULT"
fi

# T11.3: parse_youtube_url — shorts
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import parse_youtube_url
r = parse_youtube_url('https://www.youtube.com/shorts/dQw4w9WgXcQ')
assert r['type'] == 'video', f'type: {r[\"type\"]}'
assert r['video_id'] == 'dQw4w9WgXcQ', f'id: {r[\"video_id\"]}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.3 parse_youtube_url: shorts"
else
    fail "T11.3 parse_youtube_url shorts" "$RESULT"
fi

# T11.4: parse_youtube_url — youtu.be short link
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import parse_youtube_url
r = parse_youtube_url('https://youtu.be/dQw4w9WgXcQ')
assert r['type'] == 'video', f'type: {r[\"type\"]}'
assert r['video_id'] == 'dQw4w9WgXcQ', f'id: {r[\"video_id\"]}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.4 parse_youtube_url: youtu.be short link"
else
    fail "T11.4 parse_youtube_url youtu.be" "$RESULT"
fi

# T11.5: parse_youtube_url — unknown URL returns type=unknown
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import parse_youtube_url
r = parse_youtube_url('https://example.com/not-youtube')
assert r['type'] == 'unknown', f'type: {r[\"type\"]}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.5 parse_youtube_url: unknown URL"
else
    fail "T11.5 parse_youtube_url unknown" "$RESULT"
fi

# T11.6: format_timestamp
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import format_timestamp
assert format_timestamp(0) == '00:00', f'got {format_timestamp(0)}'
assert format_timestamp(65) == '01:05', f'got {format_timestamp(65)}'
assert format_timestamp(3661) == '01:01:01', f'got {format_timestamp(3661)}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.6 format_timestamp"
else
    fail "T11.6 format_timestamp" "$RESULT"
fi

# T11.7: format_transcript
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import format_transcript
segs = [
    {'text': 'Hello world', 'start': 0.0, 'duration': 2.0},
    {'text': 'Second segment', 'start': 5.0, 'duration': 3.0},
]
result = format_transcript(segs, include_timestamps=True)
assert '[00:00]' in result, 'Missing timestamp'
assert 'Hello world' in result, 'Missing text'
assert '[00:05]' in result, 'Missing second timestamp'

# Without timestamps
result_no_ts = format_transcript(segs, include_timestamps=False)
assert '[' not in result_no_ts, 'Timestamps should not appear'
assert 'Hello world' in result_no_ts, 'Text missing'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.7 format_transcript"
else
    fail "T11.7 format_transcript" "$RESULT"
fi

# T11.8: detect_visual_references
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import detect_visual_references
segs = [
    {'text': 'As you can see on this chart, revenue is up', 'start': 10.0},
    {'text': 'Let me explain the concept', 'start': 20.0},
    {'text': 'If you look at the data shows growth', 'start': 30.0},
]
refs = detect_visual_references(segs)
assert len(refs) == 2, f'Expected 2 refs, got {len(refs)}'
assert refs[0]['timestamp'] == 10.0
assert refs[1]['timestamp'] == 30.0
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.8 detect_visual_references"
else
    fail "T11.8 detect_visual_references" "$RESULT"
fi

# T11.9: group_segments_by_interval
RESULT=$(container_python "
from usr.plugins.youtube_transcribe.helpers.youtube_client import group_segments_by_interval
segs = [
    {'text': 'First', 'start': 10.0},
    {'text': 'Second', 'start': 50.0},
    {'text': 'Third', 'start': 310.0},
]
groups = group_segments_by_interval(segs, 300)
assert len(groups) == 2, f'Expected 2 groups, got {len(groups)}'
assert 'First' in groups[0]['text']
assert 'Second' in groups[0]['text']
assert 'Third' in groups[1]['text']

# Empty segments
empty = group_segments_by_interval([], 300)
assert empty == [], f'Expected empty, got {empty}'
print('ok')
")
if echo "$RESULT" | grep -q "ok"; then
    pass "T11.9 group_segments_by_interval"
else
    fail "T11.9 group_segments_by_interval" "$RESULT"
fi

# T11.10: CSRF required on API handler (source code check)
RESULT=$(container_python "
import ast, os, glob
api_dir = '/a0/usr/plugins/youtube_transcribe/api'
files = glob.glob(api_dir + '/*.py')
all_csrf = True
for f in files:
    if '__pycache__' in f:
        continue
    src = open(f).read()
    if 'class ' in src and 'ApiHandler' in src:
        if 'requires_csrf' not in src or 'return False' in src:
            all_csrf = False
            print(f'MISSING:{os.path.basename(f)}')
if all_csrf:
    print('ALL_CSRF')
")
if echo "$RESULT" | grep -q "ALL_CSRF"; then
    pass "T11.10 All API handlers require CSRF (source verified)"
else
    fail "T11.10 CSRF enforcement in source" "$RESULT"
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                  TEST RESULTS                       ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════╣${NC}"
TOTAL=$((PASSED + FAILED + SKIPPED))
echo -e "${CYAN}║${NC}  Total:   ${TOTAL}"
echo -e "${CYAN}║${NC}  ${GREEN}Passed:  ${PASSED}${NC}"
echo -e "${CYAN}║${NC}  ${RED}Failed:  ${FAILED}${NC}"
echo -e "${CYAN}║${NC}  ${YELLOW}Skipped: ${SKIPPED}${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"

if [ "$FAILED" -gt 0 ]; then
    echo -e "\n${RED}Failed tests:${NC}${ERRORS}"
fi

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}${FAILED} test(s) failed.${NC}"
    exit 1
fi
