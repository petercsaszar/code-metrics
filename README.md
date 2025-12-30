# Automated analysis of software metrics and complexity in student projects using static analysis

A tool for downloading gitlab projects from groups, finding milestones and then compute, visualize and compare different code metrics on them.

## Currently implemented metrics
- Bumpy Road Code Smell
- Function parameter count
- LCOM4 metrics
- LCOM5 metrics

## Usage
See the subfolders:

- Code Metrics Analyzer: `CodeMetricsAnalyzer/`
- Automated git downloader and analyzer: `bulk_analyzer/`

## Docker image with bundled analyzer

This repository includes a `docker/Dockerfile` that builds a multi-stage image containing the .NET `CodeMetricsAnalyzer` and the Python `bulk_analyzer` package. Building and using the image lets you run multiple analyzer containers in parallel without copying the analyzer sources at runtime.

Build the image locally:

```bash
docker build -t code-metrics-analyzer:local -f docker/Dockerfile .
```

Run the public analyzer (the script will launch one or more containers):

```powershell
$env:DOCKER_IMAGE = 'code-metrics-analyzer:local'
cd bulk_analyzer
python public_project_analyzer.py
```

Concurrency
- The number of parallel container runs is configurable in `bulk_analyzer/config.yml` under `public_analyzer.concurrency` (default 4).
- The analyzer image contains the analyzer binaries and Python environment; the host script mounts only a per-run temporary directory for the repository under analysis, enabling safe concurrent runs.
