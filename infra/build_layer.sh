#!/bin/bash
set -e
echo "Building strands-agents Lambda Layer..."
rm -rf infra/layer_build
mkdir -p infra/layer_build/python

# Resolve docker binary — prefer PATH, fall back to Docker Desktop on macOS.
DOCKER="$(command -v docker 2>/dev/null || echo "")"
if [ -z "$DOCKER" ] && [ -x "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  DOCKER="docker"
fi
if [ -z "$DOCKER" ]; then
  echo "Error: docker not found. Install Docker Desktop or add docker to PATH." >&2
  exit 1
fi

$DOCKER run --rm \
  --platform linux/amd64 \
  -v "$(pwd)/infra/layer_build/python:/out" \
  python:3.12-slim \
  bash -c "pip install strands-agents strands-agents-tools --target /out --no-cache-dir && rm -rf /out/*.dist-info /out/__pycache__"

echo "Layer size: $(du -sh infra/layer_build/python | cut -f1)"
echo "Done."
