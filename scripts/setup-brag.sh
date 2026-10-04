#!/usr/bin/env bash
set -euo pipefail

echo "Diaglob /brag setup"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required. Install Node.js 22+ and run this script again." >&2
  exit 1
fi

NODE_MAJOR="$(node --version | sed 's/^v//' | cut -d. -f1)"
if [ "$NODE_MAJOR" -lt 22 ]; then
  echo "Node.js 22+ is required. Current version: $(node --version)" >&2
  exit 1
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx was not found. Reinstall Node.js/npm and run this script again." >&2
  exit 1
fi

echo
echo "Installing /brag project-scoped from latent-spaces/brag..."
npx skills add https://github.com/latent-spaces/brag --skill brag

echo
if command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg: OK"
else
  echo "WARNING: FFmpeg is not on PATH. Install FFmpeg before rendering the final video."
fi

echo
echo "Checking Hyperframes..."
if ! npx hyperframes doctor; then
  echo "WARNING: Hyperframes doctor reported an issue. Resolve it before rendering." >&2
fi

echo
echo "/brag is ready for the Diaglob project."
echo "See docs/marketing/BRAG.md for the first vertical-video prompt."
