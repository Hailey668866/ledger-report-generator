#!/usr/bin/env bash
set -euo pipefail

if ! [[ "$(uname -s)" == "Darwin" ]]; then
  echo "The macOS application must be built on macOS." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"
APP_NAME="台账报表生成器"
APP_BUNDLE="$APP_NAME.app"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"
VENV_DIR="$ROOT_DIR/.venv-macos"

case "$TARGET_ARCH" in
  arm64|x86_64) ;;
  *)
    echo "Unsupported target architecture: $TARGET_ARCH" >&2
    exit 1
    ;;
esac

if ! [[ "$(uname -m)" == "$TARGET_ARCH" ]]; then
  echo "This build must run on a native $TARGET_ARCH macOS runner." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
. "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest -q
bash scripts/make_icns.sh

rm -rf -- "$BUILD_DIR" "$DIST_DIR"
python -m PyInstaller \
  --clean \
  --noconfirm \
  --workpath "$BUILD_DIR" \
  --distpath "$DIST_DIR" \
  packaging/ledger_reporter.spec

APP_PATH="$DIST_DIR/$APP_BUNDLE"
APP_EXECUTABLE="$APP_PATH/Contents/MacOS/$APP_NAME"
INFO_PLIST="$APP_PATH/Contents/Info.plist"
test -x "$APP_EXECUTABLE"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$INFO_PLIST")" \
  = "com.local.ledger-report-generator"

SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ledger-reporter-smoke.XXXXXX")"
SMOKE_READY_FILE="$SMOKE_DIR/ready"
SMOKE_LOG_FILE="$SMOKE_DIR/app.log"
APP_PID=""
cleanup_smoke() {
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
  rm -rf -- "$SMOKE_DIR"
}
trap cleanup_smoke EXIT
LEDGER_REPORTER_DATA_DIR="$SMOKE_DIR/data" \
  LEDGER_REPORTER_SMOKE_READY_FILE="$SMOKE_READY_FILE" \
  QT_QPA_PLATFORM=offscreen \
  "$APP_EXECUTABLE" >"$SMOKE_LOG_FILE" 2>&1 &
APP_PID=$!

SMOKE_READY=0
for _ in {1..100}; do
  if [[ -f "$SMOKE_READY_FILE" ]]; then
    SMOKE_READY=1
    break
  fi
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    if wait "$APP_PID"; then
      APP_EXIT=0
    else
      APP_EXIT=$?
    fi
    APP_PID=""
    echo "Packaged application exited before signalling readiness (exit $APP_EXIT)." >&2
    cat -- "$SMOKE_LOG_FILE" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ "$SMOKE_READY" -ne 1 ]]; then
  echo "Packaged application did not signal readiness within 10 seconds." >&2
  cat -- "$SMOKE_LOG_FILE" >&2
  exit 1
fi

kill "$APP_PID"
wait "$APP_PID" 2>/dev/null || true
APP_PID=""
cleanup_smoke
trap - EXIT

cp "$ROOT_DIR/docs/INSTALL_MACOS.md" "$DIST_DIR/安装说明.md"
DMG_BASENAME="$APP_NAME-$TARGET_ARCH.dmg"
CHECKSUM_BASENAME="$DMG_BASENAME.sha256"
DMG_PATH="$DIST_DIR/$DMG_BASENAME"
CHECKSUM_PATH="$DIST_DIR/$CHECKSUM_BASENAME"
rm -f -- "$DMG_PATH" "$CHECKSUM_PATH"
dmgbuild -s packaging/dmg_settings.py "$APP_NAME" "$DMG_PATH"

MOUNT_POINT="$(mktemp -d "${TMPDIR:-/tmp}/ledger-reporter-dmg.XXXXXX")"
DMG_ATTACHED=0
cleanup_mount() {
  if [[ "$DMG_ATTACHED" -eq 1 ]]; then
    hdiutil detach "$MOUNT_POINT" >/dev/null
  fi
  rmdir "$MOUNT_POINT" 2>/dev/null || true
}
trap cleanup_mount EXIT

hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT_POINT" "$DMG_PATH" >/dev/null
DMG_ATTACHED=1
test -d "$MOUNT_POINT/$APP_BUNDLE"
test -L "$MOUNT_POINT/Applications"
test -f "$MOUNT_POINT/安装说明.md"
hdiutil detach "$MOUNT_POINT" >/dev/null
DMG_ATTACHED=0
rmdir "$MOUNT_POINT"
trap - EXIT

(
  cd "$DIST_DIR"
  shasum -a 256 "$DMG_BASENAME" > "$CHECKSUM_BASENAME"
)
echo "Built $DMG_PATH"
echo "Checksum: $CHECKSUM_PATH"
