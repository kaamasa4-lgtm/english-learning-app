#!/usr/bin/env bash
# 全コンポーネントの動作確認スクリプト
# 使い方: cd backend && bash scripts/verify.sh

set -uo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$(cd "$BACKEND_DIR/../frontend" && pwd)"
REPORT="$BACKEND_DIR/../VERIFICATION_RESULTS.txt"
PASS=0
FAIL=0
SKIP=0

log() { echo "$@" | tee -a "$REPORT"; }
pass() { PASS=$((PASS + 1)); log "  [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); log "  [FAIL] $1"; }
skip() { SKIP=$((SKIP + 1)); log "  [SKIP] $1"; }

: > "$REPORT"
log "=== English Learning App Verification ==="
log "Date: $(date -Iseconds)"
log "Backend: $BACKEND_DIR"
log ""

cd "$BACKEND_DIR"

# --- 1. Environment ---
log "=== 1. Environment ==="
if [ -d .venv ] && [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
  pass ".venv exists"
else
  PY=python3
  skip ".venv not found (using system python3)"
fi

if $PY --version >> "$REPORT" 2>&1; then
  pass "Python available"
else
  fail "Python not available"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  pass "ffmpeg installed"
else
  fail "ffmpeg not found (sudo apt install ffmpeg)"
fi

if command -v ollama >/dev/null 2>&1; then
  pass "ollama CLI installed"
else
  skip "ollama CLI not found"
fi

for pkg in fastapi faster_whisper httpx uvicorn pydub; do
  if $PY -c "import ${pkg//-/_}" 2>/dev/null; then
    pass "Python package: $pkg"
  else
    fail "Python package missing: $pkg (pip install -r requirements.txt)"
  fi
done

if $PY -c "from melo.api import TTS" 2>/dev/null; then
  pass "MeloTTS (melo) installed"
else
  fail "MeloTTS not installed (required — see README)"
fi

log ""

# --- 2. Imports ---
log "=== 2. Service imports ==="
if $PY -c "
from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService
print('imports ok')
" >> "$REPORT" 2>&1; then
  pass "All service modules import successfully"
else
  fail "Service import failed (see log)"
fi

log ""

# --- 3. Storage directories ---
log "=== 3. Storage directories ==="
for dir in storage/raw_audio storage/processed_wav; do
  if [ -d "$dir" ]; then
    pass "Directory exists: $dir"
  else
    mkdir -p "$dir"
    pass "Created directory: $dir"
  fi
done

log ""

# --- 4. Ollama connectivity ---
log "=== 4. Ollama connectivity ==="
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  pass "Ollama API reachable (localhost:11434)"
  curl -s http://localhost:11434/api/tags | head -c 200 >> "$REPORT" 2>&1
  log ""
else
  skip "Ollama not running (start with: ollama serve)"
fi

log ""

# --- 5. Start uvicorn if needed ---
log "=== 5. FastAPI server ==="
UVICORN_PID=""
if ss -tln 2>/dev/null | grep -q ':8000 ' || netstat -tln 2>/dev/null | grep -q ':8000 '; then
  pass "Port 8000 already in use (assuming uvicorn is running)"
else
  if [ -x .venv/bin/uvicorn ]; then
    nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn-verify.log 2>&1 &
    UVICORN_PID=$!
    sleep 4
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      pass "Started uvicorn (PID $UVICORN_PID)"
    else
      fail "Failed to start uvicorn (see /tmp/uvicorn-verify.log)"
    fi
  else
    fail "uvicorn not found in .venv"
  fi
fi

log ""

# --- 6. HTTP endpoints ---
log "=== 6. HTTP endpoints ==="
HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "")
if echo "$HEALTH" | grep -q '"status"'; then
  pass "GET /health -> $HEALTH"
else
  fail "GET /health failed"
fi

ROOT=$(curl -sf http://localhost:8000/ 2>/dev/null || echo "")
if echo "$ROOT" | grep -q 'running'; then
  pass "GET / -> OK"
else
  fail "GET / failed"
fi

WEBM=$(ls storage/raw_audio/*.webm 2>/dev/null | head -1 || true)
if [ -n "$WEBM" ]; then
  UPLOAD=$(curl -sf -F "audio=@$WEBM" http://localhost:8000/upload-audio 2>/dev/null || echo "")
  if echo "$UPLOAD" | grep -q '"transcript"'; then
    pass "POST /upload-audio (STT+LLM pipeline) with $WEBM"
    if echo "$UPLOAD" | grep -q '"audio_url"'; then
      AUDIO_URL=$(echo "$UPLOAD" | $PY -c "import sys,json; d=json.load(sys.stdin); print(d.get('audio_url') or '')" 2>/dev/null || true)
      if [ -n "$AUDIO_URL" ] && [ "$AUDIO_URL" != "None" ]; then
        if curl -sf "http://localhost:8000$AUDIO_URL" -o /dev/null 2>/dev/null; then
          pass "TTS audio file served at $AUDIO_URL"
        else
          skip "audio_url returned but file not served: $AUDIO_URL"
        fi
      else
        skip "audio_url is null (MeloTTS may not be installed)"
      fi
    fi
  else
    fail "POST /upload-audio failed (is Ollama running? model pulled?)"
    log "  Response: ${UPLOAD:0:300}"
  fi
else
  skip "No .webm in storage/raw_audio/ — record via frontend to test upload"
fi

log ""

# --- 7. TTS direct test ---
log "=== 7. TTS direct test ==="
TTS_RESULT=$($PY -c "
from services.tts_service import TTSService
t = TTSService()
r = t.synthesize_feedback('テストです。発音の確認をしています。')
print(r)
" 2>> "$REPORT" || echo "FAIL")

if [ "$TTS_RESULT" = "FAIL" ] || [ -z "$TTS_RESULT" ]; then
  fail "TTS direct test failed"
else
  if [ -f "storage/processed_wav/$TTS_RESULT" ]; then
    pass "TTS generated: storage/processed_wav/$TTS_RESULT"
  else
    fail "TTS returned filename but file missing: $TTS_RESULT"
  fi
fi

log ""

# --- 8. Frontend ---
log "=== 8. Frontend ==="
if [ -f "$FRONTEND_DIR/index.html" ]; then
  pass "frontend/index.html exists"
else
  fail "frontend/index.html missing"
fi

if [ -f "$FRONTEND_DIR/css/style.css" ]; then
  pass "frontend/css/style.css exists"
else
  fail "frontend/css/style.css missing"
fi

if ss -tln 2>/dev/null | grep -q ':5500 ' || netstat -tln 2>/dev/null | grep -q ':5500 '; then
  pass "Port 5500 in use (frontend server running)"
else
  skip "Frontend server not running (cd frontend && python -m http.server 5500)"
fi

log ""
log "=== Summary ==="
log "PASS: $PASS | FAIL: $FAIL | SKIP: $SKIP"
log "Full log: $REPORT"

if [ -n "$UVICORN_PID" ]; then
  kill "$UVICORN_PID" 2>/dev/null || true
fi

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
