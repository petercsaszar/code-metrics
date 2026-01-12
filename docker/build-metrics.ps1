# Build Metrics.exe from dotnet/roslyn-analyzers repo (Windows)
# This script clones the repo, builds Metrics.exe, and extracts it

$ErrorActionPreference = 'Stop'

$metricsVersion = $env:METRICS_VERSION -or 'latest'
$outputDir = $env:OUTPUT_DIR -or 'C:\opt\metrics'
$buildDir = 'C:\tmp\roslyn-build'

Write-Host "🔨 Building Metrics.exe from dotnet/roslyn-analyzers..."

# Clean and create build directory
if (Test-Path $buildDir) {
    Remove-Item $buildDir -Recurse -Force
}
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Set-Location $buildDir

Write-Host "📥 Cloning dotnet/roslyn-analyzers..."
git clone --depth 1 --filter=blob:none --sparse https://github.com/dotnet/roslyn.git .
git sparse-checkout set src/RoslynAnalyzers/Tools/Metrics

# Restore and build
Write-Host "🔧 Restoring dependencies..."
dotnet restore src/RoslynAnalyzers/Tools/MetricsMetrics.csproj

Write-Host "🏗️  Building Metrics.csproj..."
dotnet build src/RoslynAnalyzers/Tools/Metrics/Metrics.csproj -c Release

# Copy the executable
$builtExe = Get-ChildItem -Path . -Recurse -Include "Metrics.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $builtExe) {
    Write-Error "❌ Metrics.exe not found!"
    exit 1
}

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
Copy-Item $builtExe.FullName -Destination "$outputDir\Metrics.exe"

Write-Host "✅ Metrics.exe built successfully: $outputDir\Metrics.exe"
Remove-Item $buildDir -Recurse -Force
