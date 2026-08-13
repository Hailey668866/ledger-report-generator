#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE="${1:-$ROOT_DIR/src/ledger_reporter/resources/app-icon.png}"
OUTPUT="${2:-$ROOT_DIR/packaging/app-icon.icns}"

if ! [[ "$(uname -s)" == "Darwin" ]]; then
  echo "ICNS icons must be built on macOS." >&2
  exit 1
fi

for command in sips iconutil; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required macOS tool is unavailable: $command" >&2
    exit 1
  }
done

if [[ ! -f "$SOURCE" ]]; then
  echo "Icon source does not exist: $SOURCE" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ledger-reporter-icon.XXXXXX")"
trap 'rm -rf -- "$TEMP_DIR"' EXIT
ICONSET="$TEMP_DIR/app.iconset"
mkdir -p "$ICONSET" "$(dirname "$OUTPUT")"

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$SOURCE" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$SOURCE" \
    --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET" -o "$OUTPUT"
