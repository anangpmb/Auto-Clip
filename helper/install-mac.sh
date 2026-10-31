#!/bin/bash
# AutoClip Web: one-time setup for macOS.
# Creates ~/AutoClip (helper + its own Python environment with yt-dlp) and an "AutoClip"
# launcher on the Desktop. Run it again any time to update.
#
#   curl -fsSL https://USERNAME.github.io/REPO/install-mac.sh | bash -s https://USERNAME.github.io/REPO/
set -euo pipefail

APP_URL="${1:-https://anangpmb.github.io/Auto-Clip/}"
case "$APP_URL" in */) ;; *) APP_URL="$APP_URL/" ;; esac
DIR="$HOME/AutoClip"
LAUNCHER="$HOME/Desktop/AutoClip.command"

step() { printf '\n==> %s\n' "$1"; }

# yt-dlp needs Python 3.10+; the python3 that ships with Xcode tools is older.
PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$(command -v "$c")"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 atau lebih baru belum terpasang."
  echo "Install dari https://www.python.org/downloads/macos/ lalu jalankan perintah ini lagi."
  open "https://www.python.org/downloads/macos/" || true
  exit 1
fi
step "Memakai $("$PY" --version) di $PY"

# A private venv avoids Homebrew's "externally managed environment" pip error.
step "Menyiapkan Python + yt-dlp di $DIR/venv (bisa beberapa menit)"
mkdir -p "$DIR"
"$PY" -m venv "$DIR/venv"
"$DIR/venv/bin/python" -m pip install --quiet --upgrade pip
"$DIR/venv/bin/python" -m pip install --quiet --upgrade "yt-dlp[default,deno]"

step "Mengunduh helper dari $APP_URL"
curl -fsSL -o "$DIR/autoclip_helper.py" "${APP_URL}autoclip_helper.py"

step "Membuat launcher di $LAUNCHER"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# AutoClip: menjalankan helper lalu membuka web app di browser.
# Tutup jendela Terminal ini untuk mematikan helper.
DIR="\$HOME/AutoClip"
APP_URL="$APP_URL"
export PATH="\$DIR/venv/bin:\$PATH"
# Ambil helper terbaru dari web app; kalau offline, pakai yang lama.
if curl -fsSL --max-time 8 -o "\$DIR/autoclip_helper.py.new" "\${APP_URL}autoclip_helper.py"; then
  mv "\$DIR/autoclip_helper.py.new" "\$DIR/autoclip_helper.py"
fi
exec "\$DIR/venv/bin/python" "\$DIR/autoclip_helper.py" --app "\$APP_URL" --open
EOF
chmod +x "$LAUNCHER"

step "Selesai!"
echo "Klik dua kali 'AutoClip' di Desktop: helper menyala dan web app terbuka di browser."
echo "Launcher-nya bisa diseret ke Dock supaya lebih mudah dibuka."
