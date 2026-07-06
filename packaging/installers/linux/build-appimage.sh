#!/usr/bin/env bash
# Build SentinelGUI-x86_64.AppImage from the PyInstaller onedir output (Linux).
#
# Lays out an AppDir from dist/SentinelGUI/, installs the .desktop file and the
# 256px launcher icon, then runs linuxdeploy to emit an AppImage. Downloads
# linuxdeploy if it is not already on PATH / in the working dir.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DIST="${REPO_ROOT}/dist/SentinelGUI"
APPDIR="${REPO_ROOT}/dist/AppDir"
ICON_SRC="${REPO_ROOT}/packaging/build-icons/256.png"
DESKTOP_SRC="${REPO_ROOT}/packaging/installers/linux/sentinelgui.desktop"

if [[ ! -d "${DIST}" ]]; then
  echo "error: ${DIST} not found; run pyinstaller first" >&2
  exit 1
fi

# --- lay out the AppDir -----------------------------------------------------
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Copy the whole onedir bundle next to the launcher.
cp -r "${DIST}/." "${APPDIR}/usr/bin/"

cp "${DESKTOP_SRC}" "${APPDIR}/usr/share/applications/sentinelgui.desktop"
cp "${ICON_SRC}" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/sentinelgui.png"

# linuxdeploy also wants the icon + desktop at the AppDir root.
cp "${ICON_SRC}" "${APPDIR}/sentinelgui.png"
cp "${DESKTOP_SRC}" "${APPDIR}/sentinelgui.desktop"

# --- fetch linuxdeploy if needed --------------------------------------------
LINUXDEPLOY="${REPO_ROOT}/dist/linuxdeploy-x86_64.AppImage"
if ! command -v linuxdeploy >/dev/null 2>&1 && [[ ! -x "${LINUXDEPLOY}" ]]; then
  echo "downloading linuxdeploy..."
  curl -fsSL -o "${LINUXDEPLOY}" \
    "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
  chmod +x "${LINUXDEPLOY}"
fi
LD_BIN="$(command -v linuxdeploy || echo "${LINUXDEPLOY}")"

# --- build ------------------------------------------------------------------
cd "${REPO_ROOT}/dist"
export OUTPUT="SentinelGUI-x86_64.AppImage"
"${LD_BIN}" --appdir "${APPDIR}" \
  --desktop-file "${APPDIR}/sentinelgui.desktop" \
  --icon-file "${APPDIR}/sentinelgui.png" \
  --output appimage

echo "wrote ${REPO_ROOT}/dist/${OUTPUT}"
