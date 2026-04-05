#!/usr/bin/env bash
# Build a Lambda layer containing WeasyPrint + system dependencies (Cairo, Pango).
# Outputs to infra/weasyprint_layer/ for CDK deployment.
#
# Usage: bash infra/build_weasyprint_layer.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAYER_DIR="$SCRIPT_DIR/weasyprint_layer"

echo "==> Building WeasyPrint Lambda layer..."

# Detect Docker binary (same pattern as build_layer.sh)
if command -v docker &>/dev/null; then
  DOCKER=docker
elif [ -x "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
  DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
else
  echo "ERROR: Docker not found. Install Docker Desktop or add docker to PATH."
  exit 1
fi

# Clean previous build
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR"

# Build in Amazon Linux 2023 container (matches Lambda Python 3.12 runtime)
$DOCKER run --rm \
  --platform linux/amd64 \
  -v "$LAYER_DIR:/out" \
  public.ecr.aws/lambda/python:3.12 \
  bash -c '
    set -e

    # Install system dependencies for WeasyPrint
    dnf install -y \
      cairo cairo-devel \
      pango pango-devel \
      gdk-pixbuf2 gdk-pixbuf2-devel \
      fontconfig freetype \
      libffi-devel \
      gcc python3-devel 2>/dev/null

    # Install WeasyPrint + Jinja2 into the layer
    pip install weasyprint jinja2 --target /out/python --no-cache-dir

    # Copy required shared libraries
    mkdir -p /out/lib
    for lib in libcairo.so* libpango*.so* libgobject*.so* libglib*.so* \
               libfontconfig.so* libfreetype.so* libpixman*.so* \
               libharfbuzz.so* libfribidi.so* libpng*.so* \
               libgdk_pixbuf*.so* libgio*.so* libgmodule*.so*; do
      find /usr/lib64 -name "$lib" -exec cp -P {} /out/lib/ \; 2>/dev/null || true
    done

    # Clean up caches
    find /out -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find /out -type d -name tests -exec rm -rf {} + 2>/dev/null || true

    echo "==> Layer contents:"
    du -sh /out/python /out/lib
  '

echo "==> WeasyPrint layer built at $LAYER_DIR"
du -sh "$LAYER_DIR"
