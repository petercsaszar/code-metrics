#!/bin/bash
# Build Metrics.exe from dotnet/roslyn-analyzers repo
# This script clones the repo, builds Metrics.exe, and extracts it

set -eu

METRICS_VERSION="${METRICS_VERSION:-latest}"
OUTPUT_DIR="${OUTPUT_DIR:-/opt/metrics}"
BUILD_DIR="/tmp/roslyn-build"

echo "🔨 Building Metrics.exe from dotnet/roslyn-analyzers..."

# Clone repo
if [ -d "$BUILD_DIR" ]; then
    rm -rf "$BUILD_DIR"
fi
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "📥 Cloning dotnet/roslyn-analyzers..."
git clone --depth 1 --filter=blob:none --sparse https://github.com/dotnet/roslyn-analyzers.git .
git sparse-checkout set src/Tools/Metrics

# Restore and build
echo "🔧 Restoring dependencies..."
dotnet restore src/Tools/Metrics/Metrics.csproj

echo "🏗️  Building Metrics.csproj..."
dotnet build src/Tools/Metrics/Metrics.csproj -c Release

# Copy the executable
BUILT_EXE=$(find . -name "Metrics.exe" -o -name "Metrics" -type f | head -1)
if [ -z "$BUILT_EXE" ]; then
    echo "❌ Metrics executable not found!"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
cp "$BUILT_EXE" "$OUTPUT_DIR/Metrics"
chmod +x "$OUTPUT_DIR/Metrics"

echo "✅ Metrics tool built successfully: $OUTPUT_DIR/Metrics"
rm -rf "$BUILD_DIR"
