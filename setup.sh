#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/sl33p-space"
SERVICE_NAME="sl33p-space"
USER_NAME="sl33p"

echo "──────────────────────────────"
echo "  sl33p-space installer"
echo "──────────────────────────────"
echo

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo "Run this script with sudo:"
  echo "  sudo bash setup.sh"
  exit 1
fi

# Check Python 3.10+
if ! command -v python3 &>/dev/null; then
  echo "Python 3 not found. Installing..."
  apt-get update && apt-get install -y python3 python3-venv python3-pip
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ]]; then
  echo "Python 3.10+ required (found $PY_VERSION)"
  exit 1
fi
echo "[ok] Python $PY_VERSION"

# Install system audio dependencies
echo "Installing audio packages..."
apt-get update -qq
apt-get install -y -qq alsa-utils mpg123 ffmpeg

# Create service user
if ! id "$USER_NAME" &>/dev/null; then
  useradd --system --shell /usr/sbin/nologin --home-dir "$INSTALL_DIR" "$USER_NAME"
  echo "[ok] Created user: $USER_NAME"
else
  echo "[ok] User $USER_NAME already exists"
fi

# Copy project files
if [[ "$(pwd)" != "$INSTALL_DIR" ]]; then
  mkdir -p "$INSTALL_DIR"
  cp -r . "$INSTALL_DIR/"
  echo "[ok] Copied to $INSTALL_DIR"
else
  echo "[ok] Already in $INSTALL_DIR"
fi

# Create venv and install deps
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
echo "[ok] Dependencies installed"

# Prompt for API keys
echo
echo "── API Keys ──"
echo "The Gemini API key is required for the AI agent."
echo "Get one at: https://aistudio.google.com/apikey"
echo

read -rp "GOOGLE_API_KEY: " GOOGLE_KEY
if [[ -z "$GOOGLE_KEY" ]]; then
  echo "Warning: No API key provided. Agent will run in fallback mode."
  GOOGLE_KEY=""
fi

read -rp "NASA_API_KEY (Enter to skip, uses DEMO_KEY): " NASA_KEY
NASA_KEY="${NASA_KEY:-DEMO_KEY}"

# Write .env with restricted permissions
ENV_FILE="$INSTALL_DIR/.env"
cat > "$ENV_FILE" <<EOF
GOOGLE_API_KEY=$GOOGLE_KEY
NASA_API_KEY=$NASA_KEY
EOF
chmod 600 "$ENV_FILE"
echo "[ok] Keys saved to $ENV_FILE (mode 600)"

# Create data directories
mkdir -p "$INSTALL_DIR/data/sounds" "$INSTALL_DIR/data/music"

# Set ownership
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

# Add sl33p user to audio group
usermod -aG audio "$USER_NAME" 2>/dev/null || true

# Install systemd service
cp "$INSTALL_DIR/sl33p-space.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"
echo "[ok] Service installed and started"

# Get hostname
HOSTNAME=$(hostname)
PORT=8090

echo
echo "──────────────────────────────"
echo "  sl33p-space is running!"
echo
echo "  Local:   http://localhost:$PORT"
echo "  Network: http://$HOSTNAME.local:$PORT"
echo
echo "  Logs:    journalctl -u $SERVICE_NAME -f"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "──────────────────────────────"
