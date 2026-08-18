@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo GeoPilot Frontend Encoding Cleanup V1
echo Controlled mojibake repair + source audit
echo ============================================================
echo.

docker compose config --services >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: run from geopilot_v7 project root and ensure Docker is running.
  exit /b 1
)

echo [1/5] Repairing known mojibake sequences...
docker compose run --rm --no-deps -v "%CD%:/workspace" -w /workspace backend python -c "import base64;exec(base64.b64decode('CmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgc2h1dGlsCmZyb20gZGF0ZXRpbWUgaW1wb3J0IGRhdGV0aW1lCgpST09UID0gUGF0aCgiL3dvcmtzcGFjZSIpClNSQyA9IFJPT1QgLyAiZnJvbnRlbmQiIC8gInNyYyIKaWYgbm90IFNSQy5pc19kaXIoKToKICAgIHJhaXNlIFN5c3RlbUV4aXQoIkJMT0NLRUQ6IGZyb250ZW5kL3NyYyBub3QgZm91bmQuIikKCmV4dGVuc2lvbnMgPSB7Ii50cyIsICIudHN4IiwgIi5qcyIsICIuanN4IiwgIi5jc3MiLCAiLmh0bWwiLCAiLmpzb24ifQoKIyBFeHBsaWNpdCBrbm93biBVVEYtOCBtb2ppYmFrZSBzZXF1ZW5jZXMgLT4gaW50ZW5kZWQgVW5pY29kZS4KIyBXcml0dGVuIHdpdGggZXNjYXBlcyBzbyB0aGUgcGF0Y2hlciBpdHNlbGYgaXMgZW5jb2Rpbmctc2FmZS4KcmVwbGFjZW1lbnRzID0gewogICAgIlx1MDBjMlx1MDBiNyI6ICJcdTAwYjciLCAgICAgICAgICAgICAgIyDDgsK3IC0+IMK3CiAgICAiXHUwMGUyXHUyMDIwXHUyMDE5IjogIlx1MjE5MiIsICAgICAgICMgw6LigKDigJkgLT4g4oaSCiAgICAiXHUwMGUyXHUyMGFjXHUwMGE2IjogIlx1MjAyNiIsICAgICAgICMgw6LigqzCpiAtPiDigKYKICAgICJcdTAwZTJcdTIwYWNcdTIwMWQiOiAiXHUyMDE0IiwgICAgICAgIyDDouKCrOKAnSAtPiDigJQKICAgICJcdTAwZTJcdTIwYWNcdTIwMWMiOiAiXHUyMDEzIiwgICAgICAgIyDDouKCrOKAnCAtPiDigJMKICAgICJcdTAwZTJcdTIwYWNcdTAwYTIiOiAiXHUyMDIyIiwgICAgICAgIyDDouKCrMKiIC0+IOKAogogICAgIlx1MDBlMlx1MDE1M1x1MjAxYyI6ICJcdTI3MTMiLCAgICAgICAjIMOixZPigJwgLT4g4pyTCiAgICAiXHUwMGMzXHUyMDE0IjogIlx1MDBkNyIsICAgICAgICAgICAgICMgw4PigJQgLT4gw5cKfQoKZmlsZXMgPSBzb3J0ZWQocCBmb3IgcCBpbiBTUkMucmdsb2IoIioiKSBpZiBwLmlzX2ZpbGUoKSBhbmQgcC5zdWZmaXgubG93ZXIoKSBpbiBleHRlbnNpb25zKQpzdGFtcCA9IGRhdGV0aW1lLm5vdygpLnN0cmZ0aW1lKCIlWSVtJWRfJUglTSVTIikKYmFja3VwID0gUk9PVCAvICJhcnRpZmFjdHMiIC8gZiJmcm9udGVuZF9lbmNvZGluZ19iYWNrdXBfe3N0YW1wfSIKCmNoYW5nZWQgPSBbXQpjb3VudHMgPSB7fQoKZm9yIHBhdGggaW4gZmlsZXM6CiAgICB0ZXh0ID0gcGF0aC5yZWFkX3RleHQoZW5jb2Rpbmc9InV0Zi04IikKICAgIG9yaWdpbmFsID0gdGV4dAogICAgbG9jYWwgPSB7fQogICAgZm9yIGJhZCwgZ29vZCBpbiByZXBsYWNlbWVudHMuaXRlbXMoKToKICAgICAgICBuID0gdGV4dC5jb3VudChiYWQpCiAgICAgICAgaWYgbjoKICAgICAgICAgICAgdGV4dCA9IHRleHQucmVwbGFjZShiYWQsIGdvb2QpCiAgICAgICAgICAgIGxvY2FsW2JhZF0gPSBuCiAgICAgICAgICAgIGNvdW50c1tiYWRdID0gY291bnRzLmdldChiYWQsIDApICsgbgogICAgaWYgdGV4dCAhPSBvcmlnaW5hbDoKICAgICAgICByZWwgPSBwYXRoLnJlbGF0aXZlX3RvKFJPT1QpCiAgICAgICAgZGVzdCA9IGJhY2t1cCAvIHJlbAogICAgICAgIGRlc3QucGFyZW50Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgICAgICBzaHV0aWwuY29weTIocGF0aCwgZGVzdCkKICAgICAgICBwYXRoLndyaXRlX3RleHQodGV4dCwgZW5jb2Rpbmc9InV0Zi04IiwgbmV3bGluZT0iXG4iKQogICAgICAgIGNoYW5nZWQuYXBwZW5kKHN0cihyZWwpKQogICAgICAgIHByaW50KCJQQVRDSEVEOiIsIHJlbCwgbG9jYWwpCgppZiBjaGFuZ2VkOgogICAgcHJpbnQoIkJBQ0tVUDoiLCBiYWNrdXApCmVsc2U6CiAgICBwcmludCgiTk8gS05PV04gTU9KSUJBS0UgU0VRVUVOQ0VTIFJFUVVJUkVEIFBBVENISU5HLiIpCgojIEZhaWwgaWYgdGhlIGNvbW1vbiBtb2ppYmFrZSBsZWFkIGNoYXJhY3RlcnMgc3RpbGwgcmVtYWluIGluIHNvdXJjZS4KcmVtYWluaW5nID0gW10KZm9yIHBhdGggaW4gZmlsZXM6CiAgICB0ZXh0ID0gcGF0aC5yZWFkX3RleHQoZW5jb2Rpbmc9InV0Zi04IikKICAgIGZvciBsaW5lbm8sIGxpbmUgaW4gZW51bWVyYXRlKHRleHQuc3BsaXRsaW5lcygpLCAxKToKICAgICAgICBpZiBhbnkoY2ggaW4gbGluZSBmb3IgY2ggaW4gKCJcdTAwYzIiLCAiXHUwMGMzIiwgIlx1MDBlMiIpKToKICAgICAgICAgICAgcmVtYWluaW5nLmFwcGVuZCgoc3RyKHBhdGgucmVsYXRpdmVfdG8oUk9PVCkpLCBsaW5lbm8sIGxpbmUuc3RyaXAoKSkpCgpwcmludCgiVE9UQUwgTU9ESUZJRUQgRklMRVM6IiwgbGVuKGNoYW5nZWQpKQpwcmludCgiVE9UQUwgUkVQTEFDRU1FTlRTOiIsIHN1bShjb3VudHMudmFsdWVzKCkpKQoKaWYgcmVtYWluaW5nOgogICAgcHJpbnQoIlJFTUFJTklOR19TVVNQSUNJT1VTX1RFWFQ6IikKICAgIGZvciBpdGVtIGluIHJlbWFpbmluZ1s6MTAwXToKICAgICAgICBwcmludChmIntpdGVtWzBdfTp7aXRlbVsxXX06IHtpdGVtWzJdfSIpCiAgICByYWlzZSBTeXN0ZW1FeGl0KAogICAgICAgICJFTkNPRElORyBBVURJVCBCTE9DS0VEOiBzdXNwaWNpb3VzIG1vamliYWtlIGxlYWQgY2hhcmFjdGVycyByZW1haW4uICIKICAgICAgICAiTm8gYmxpbmQgcmVwbGFjZW1lbnQgd2FzIGFwcGxpZWQgdG8gdGhvc2UgY2FzZXMuIgogICAgKQoKcHJpbnQoIkVOQ09ESU5HIFNPVVJDRSBBVURJVCBQQVNTIikK'))"
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
echo ENCODING CLEANUP GATE PASS
echo Refresh GeoPilot once with Ctrl+F5.
echo Track B AI/backend/7-of-7 workflow were not modified.
echo ============================================================
exit /b 0

:fail
echo.
echo ============================================================
echo ENCODING CLEANUP GATE FAILED
echo STOP. Do not rerun blindly.
echo A timestamped backup exists under artifacts\frontend_encoding_backup_*
echo Share this terminal output.
echo ============================================================
exit /b 1
