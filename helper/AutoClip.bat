@echo off
rem AutoClip: klik dua kali untuk menjalankan helper dan membuka web app di browser.
rem Tutup jendela ini untuk mematikan helper.
setlocal
title AutoClip helper
set "APP_URL=https://anangpmb.github.io/Auto-Clip/"

python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 atau lebih baru belum terpasang.
  echo Install dari https://www.python.org/downloads/ dan centang "Add python.exe to PATH".
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)

python -c "import yt_dlp" >nul 2>nul
if errorlevel 1 (
  echo Memasang yt-dlp untuk pertama kali...
  python -m pip install -U "yt-dlp[default,deno]"
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

rem Deteksi wajah (OpenCV) dan caption (Pillow) untuk ekspor video; opsional.
python -c "import cv2, PIL" >nul 2>nul
if errorlevel 1 (
  echo Memasang komponen deteksi wajah dan caption untuk pertama kali...
  python -m pip install -U opencv-python-headless pillow
)

python "%~dp0autoclip_helper.py" --app %APP_URL% --open %*
if errorlevel 1 pause
