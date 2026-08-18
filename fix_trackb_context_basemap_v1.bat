@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Track B Context Basemap Fix V1
echo Frontend-only map enhancement
echo Basemap is visual context only - NOT analysis evidence
echo ============================================================
echo.

docker compose config --services >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: run from geopilot_v7 project root and ensure Docker is running.
  exit /b 1
)

echo [1/5] Applying controlled basemap patch...
docker compose run --rm --no-deps -v "%CD%:/workspace" -w /workspace backend python -c "import base64;exec(base64.b64decode('CmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgcmUKaW1wb3J0IHNodXRpbApmcm9tIGRhdGV0aW1lIGltcG9ydCBkYXRldGltZQoKUk9PVCA9IFBhdGgoJy93b3Jrc3BhY2UnKQpQQUdFID0gUk9PVCAvICdmcm9udGVuZC9zcmMvcGFnZXMvVHJhY2tCV29ya3NwYWNlUGFnZS50c3gnCgppZiBub3QgUEFHRS5pc19maWxlKCk6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdQQVRDSCBCTE9DS0VEOiBUcmFja0JXb3Jrc3BhY2VQYWdlLnRzeCBub3QgZm91bmQuJykKCnN0YW1wID0gZGF0ZXRpbWUubm93KCkuc3RyZnRpbWUoJyVZJW0lZF8lSCVNJVMnKQpiYWNrdXAgPSBST09UIC8gJ2FydGlmYWN0cycgLyBmJ3RyYWNrYl9iYXNlbWFwX2JhY2t1cF97c3RhbXB9JwpiYWNrdXAubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQpzaHV0aWwuY29weTIoUEFHRSwgYmFja3VwIC8gUEFHRS5uYW1lKQpwcmludCgnQkFDS1VQOicsIGJhY2t1cCkKCnRleHQgPSBQQUdFLnJlYWRfdGV4dChlbmNvZGluZz0ndXRmLTgnKQptYXJrZXIgPSAnLy8gVFJBQ0tCX0NPTlRFWFRfQkFTRU1BUF9WMScKCmlmIG1hcmtlciBub3QgaW4gdGV4dDoKICAgIHBhdHRlcm4gPSByZS5jb21waWxlKAogICAgICAgIHInc3R5bGU6XHMqXHtccyp2ZXJzaW9uOlxzKjgsXHMqc291cmNlczpccypce1xzKlx9LFxzKmxheWVyczpccypcW1xzKlx7XHMqaWQ6XHMqImJhY2tncm91bmQiLFxzKnR5cGU6XHMqImJhY2tncm91bmQiLFxzKnBhaW50OlxzKlx7XHMqImJhY2tncm91bmQtY29sb3IiOlxzKiJbXiJdKyJccypcfVxzKlx9XHMqXF0sXHMqXH0sJywKICAgICAgICByZS5TLAogICAgKQogICAgcmVwbGFjZW1lbnQgPSAnJycvLyBUUkFDS0JfQ09OVEVYVF9CQVNFTUFQX1YxCiAgICAgIC8vIFZpc3VhbCBjb250ZXh0IG9ubHkuIE5vdCB1c2VkIGJ5IGFuYWx5c2lzLCBldmlkZW5jZSBsaW5lYWdlIG9yIEFJIGdyb3VuZGluZy4KICAgICAgc3R5bGU6ICJodHRwczovL3RpbGVzLm9wZW5mcmVlbWFwLm9yZy9zdHlsZXMvbGliZXJ0eSIsJycnCiAgICB0ZXh0LCBjb3VudCA9IHBhdHRlcm4uc3VibihyZXBsYWNlbWVudCwgdGV4dCwgY291bnQ9MSkKICAgIGlmIGNvdW50ICE9IDE6CiAgICAgICAgcmFpc2UgU3lzdGVtRXhpdCgnUEFUQ0ggQkxPQ0tFRDogYmFja2dyb3VuZC1vbmx5IE1hcExpYnJlIHN0eWxlIG5vdCBmb3VuZC4nKQoKICAgIGlmICdhdHRyaWJ1dGlvbkNvbnRyb2w6IGZhbHNlLCcgaW4gdGV4dDoKICAgICAgICB0ZXh0ID0gdGV4dC5yZXBsYWNlKCdhdHRyaWJ1dGlvbkNvbnRyb2w6IGZhbHNlLCcsICdhdHRyaWJ1dGlvbkNvbnRyb2w6IHRydWUsJywgMSkKCiAgICBodWQgPSAnPHNwYW4gY2xhc3NOYW1lPSJsaXZlLWNoaXAiPmRldGVybWluaXN0aWM8L3NwYW4+JwogICAgaWYgaHVkIGluIHRleHQ6CiAgICAgICAgdGV4dCA9IHRleHQucmVwbGFjZSgKICAgICAgICAgICAgaHVkLAogICAgICAgICAgICAnPHNwYW4gY2xhc3NOYW1lPSJsaXZlLWNoaXAiPmNvbnRleHQgYmFzZW1hcCDCtyBub3QgZXZpZGVuY2U8L3NwYW4+PHNwYW4gY2xhc3NOYW1lPSJsaXZlLWNoaXAiPmRldGVybWluaXN0aWM8L3NwYW4+JywKICAgICAgICAgICAgMSwKICAgICAgICApCgogICAgUEFHRS53cml0ZV90ZXh0KHRleHQsIGVuY29kaW5nPSd1dGYtOCcsIG5ld2xpbmU9J1xuJykKICAgIHByaW50KCdQQVRDSEVEOicsIFBBR0UpCmVsc2U6CiAgICBwcmludCgnQkFTRU1BUCBQQVRDSCBBTFJFQURZIFBSRVNFTlQnKQoKcHJpbnQoJ0JBU0VNQVAgUEFUQ0ggU1RFUCBDT01QTEVURScpCg=='))"
if errorlevel 1 goto :fail

echo.
echo [2/5] TypeScript gate...
docker compose exec frontend npm run typecheck
if errorlevel 1 goto :fail

echo.
echo [3/5] Frontend production build gate...
docker compose exec frontend npm run build
if errorlevel 1 goto :fail

echo.
echo [4/5] Restarting frontend only...
docker compose restart frontend
if errorlevel 1 goto :fail

echo.
echo [5/5] Container status...
timeout /t 4 /nobreak >nul
docker compose ps
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo BASEMAP PATCH GATE PASS
echo Refresh GeoPilot with Ctrl+F5.
echo Expected: geographic basemap + change geometry + Urban/Rural toggle.
echo Backend AI, OpenAI routing, numeric grounding and 7/7 logic untouched.
echo ============================================================
exit /b 0

:fail
echo.
echo ============================================================
echo BASEMAP PATCH GATE FAILED
echo STOP. Do not rerun blindly.
echo Backup is under artifacts\trackb_basemap_backup_*
echo Share this terminal output.
echo ============================================================
exit /b 1
