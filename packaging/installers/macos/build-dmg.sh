#!/usr/bin/env bash
# Build a SentinelGUI.dmg from the PyInstaller .app bundle (macOS, CI-only).
#
# Requires `create-dmg` (brew install create-dmg) and a built dist/SentinelGUI.app.
# No codesigning / notarization is performed (no Developer ID available); the DMG
# is unsigned and users will need to right-click > Open on first launch.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
APP="${REPO_ROOT}/dist/SentinelGUI.app"
DMG="${REPO_ROOT}/dist/SentinelGUI.dmg"
ICNS="${REPO_ROOT}/packaging/build-icons/app.icns"

if [[ ! -d "${APP}" ]]; then
  echo "error: ${APP} not found; run pyinstaller first" >&2
  exit 1
fi

# create-dmg exits non-zero if the target already exists.
rm -f "${DMG}"

VOLICON_ARG=()
if [[ -f "${ICNS}" ]]; then
  VOLICON_ARG=(--volicon "${ICNS}")
fi

create-dmg \
  --volname "SentinelGUI" \
  "${VOLICON_ARG[@]}" \
  --window-pos 200 120 \
  --window-size 660 400 \
  --icon-size 100 \
  --icon "SentinelGUI.app" 160 185 \
  --hide-extension "SentinelGUI.app" \
  --app-drop-link 500 185 \
  "${DMG}" \
  "${APP}"

echo "wrote ${DMG}"
