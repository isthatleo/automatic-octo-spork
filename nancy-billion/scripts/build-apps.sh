#!/usr/bin/env bash
# Billion — one-command app builder for macOS and Linux.
#
#   ./scripts/build-apps.sh            # desktop app for whatever OS you're on
#   ./scripts/build-apps.sh desktop    # same, explicitly
#   ./scripts/build-apps.sh android    # generate + open the Android project
#   ./scripts/build-apps.sh ios        # generate + open the Xcode project (macOS only)
#   ./scripts/build-apps.sh all        # everything this machine can build
#
# Needs network on first run (npm downloads Electron / Capacitor).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-desktop}"

C_CYAN=$'\033[36m'; C_GOLD=$'\033[33m'; C_DIM=$'\033[2m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
say()  { printf '%s▸ %s%s\n' "$C_CYAN" "$1" "$C_OFF"; }
note() { printf '%s  %s%s\n' "$C_DIM" "$1" "$C_OFF"; }
die()  { printf '%s✕ %s%s\n' "$C_RED" "$1" "$C_OFF" >&2; exit 1; }

command -v node >/dev/null 2>&1 || die "Node.js not found. Install Node 18+ from https://nodejs.org and re-run."
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 18 ] || die "Node 18+ required (found $(node -v))."

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      die "Unsupported OS. On Windows use scripts\\build-apps.ps1 instead." ;;
esac

printf '\n%s  B I L L I O N%s  %sapp builder — host: %s%s\n\n' "$C_GOLD" "$C_OFF" "$C_DIM" "$OS" "$C_OFF"

build_desktop() {
  say "Desktop app ($OS)"
  cd "$ROOT/desktop"
  note "installing electron + electron-builder (first run takes a few minutes)…"
  npm install --no-audit --no-fund
  note "packaging…"
  npm run "dist:$OS"
  printf '\n%s✓ Desktop app built.%s\n' "$C_CYAN" "$C_OFF"
  note "artifacts: desktop/dist/"
  ls -1 "$ROOT/desktop/dist" 2>/dev/null | sed 's/^/    /' || true
}

build_mobile() {
  local platform="$1"
  say "Mobile app ($platform)"
  cd "$ROOT/mobile"
  note "installing capacitor…"
  npm install --no-audit --no-fund
  npx cap add "$platform" 2>/dev/null || note "$platform project already exists — reusing it."
  note "generating app icons + splash…"
  npm run assets --silent || note "icon generation skipped — the default icon will be used."
  npx cap sync "$platform"
  node scripts/patch-native.js
  printf '\n%s✓ %s project ready.%s\n' "$C_CYAN" "$platform" "$C_OFF"
  if [ "$platform" = "android" ]; then
    note "opening Android Studio — then press ▶ Run to launch the emulator."
    npx cap open android || note "Android Studio not found. Open mobile/android manually."
  else
    note "opening Xcode — then press ▶ Run to launch the simulator."
    npx cap open ios || note "Xcode not found. Open mobile/ios/App/App.xcworkspace manually."
  fi
}

case "$TARGET" in
  desktop) build_desktop ;;
  android) build_mobile android ;;
  ios)
    [ "$OS" = "mac" ] || die "iOS apps can only be built on macOS."
    build_mobile ios ;;
  all)
    build_desktop
    build_mobile android
    [ "$OS" = "mac" ] && build_mobile ios || note "iOS skipped (needs macOS)." ;;
  *) die "Unknown target '$TARGET'. Use: desktop | android | ios | all" ;;
esac

printf '\n%sRemember: the apps are a window onto your stack. Start it first with%s\n' "$C_DIM" "$C_OFF"
printf '%s  docker compose up -d%s\n\n' "$C_GOLD" "$C_OFF"
