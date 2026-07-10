#!/usr/bin/env bash
set -euo pipefail

LABEL="com.openinsects.ask-insects-tunnel"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/run_hosted_tunnel.sh"
GCLOUD_BIN="${ASK_INSECTS_GCLOUD_BIN:-$(command -v gcloud || true)}"
ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
LOCAL_PORT="${ASK_INSECTS_LOCAL_PORT:-18080}"
REMOTE_PORT="${ASK_INSECTS_REMOTE_PORT:-8080}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/ask-insects"
DOMAIN="gui/$(id -u)"

if [[ -z "$GCLOUD_BIN" || ! -x "$GCLOUD_BIN" ]]; then
  echo "gcloud is required to install the Ask Insects tunnel" >&2
  exit 1
fi
PROJECT="${ASK_INSECTS_GCP_PROJECT:-$($GCLOUD_BIN config get-value project 2>/dev/null)}"

mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"
TEMP_PLIST="$(mktemp "${TMPDIR:-/tmp}/$LABEL.XXXXXX")"
trap 'rm -f "$TEMP_PLIST"' EXIT

cat >"$TEMP_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RUN_SCRIPT</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ASK_INSECTS_GCLOUD_BIN</key>
    <string>$GCLOUD_BIN</string>
    <key>ASK_INSECTS_GCP_PROJECT</key>
    <string>$PROJECT</string>
    <key>ASK_INSECTS_GCP_ZONE</key>
    <string>$ZONE</string>
    <key>ASK_INSECTS_VM</key>
    <string>$VM</string>
    <key>ASK_INSECTS_LOCAL_PORT</key>
    <string>$LOCAL_PORT</string>
    <key>ASK_INSECTS_REMOTE_PORT</key>
    <string>$REMOTE_PORT</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/tunnel.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/tunnel.err.log</string>
</dict>
</plist>
EOF

plutil -lint "$TEMP_PLIST" >/dev/null
mv "$TEMP_PLIST" "$PLIST"
chmod 600 "$PLIST"
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo "Ask Insects tunnel installed at http://127.0.0.1:$LOCAL_PORT"
