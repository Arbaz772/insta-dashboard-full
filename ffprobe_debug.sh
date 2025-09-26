#!/usr/bin/env bash
# ffprobe_debug.sh <path-to-file>
# Writes /app/outputs/ffprobe_<basename>.json with ffprobe JSON output
set -euo pipefail
if [ $# -lt 1 ]; then
echo "Usage: $0 <video-file>"
exit 2
fi
IN="$1"
B="$(basename "$IN")"
OUT="/app/outputs/ffprobe_${B%.*}.json"
ffprobe -v quiet -print_format json -show_format -show_streams "$IN" > "$OUT" 2>&1 || echo "ffprobe exited non-zero, partial output saved to $OUT"
echo "Wrote $OUT"