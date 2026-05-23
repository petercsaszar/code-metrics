# Automated analysis of software metrics and complexity in student projects using static analysis

A tool for downloading gitlab projects from groups, finding milestones and then compute, visualize and compare different code metrics on them.

## Currently implemented metrics
- Bumpy Road Code Smell
- Functional parameter count
- LCOM4 metrics
- LCOM5 metrics
- Cyclomatic complexity
- Maintainability index
- Class coupling

## Usage
See the subfolders:

- Code Metrics Analyzer: `CodeMetricsAnalyzer/`
- Automated git downloader and analyzer: `bulk_analyzer/`

## Docker usage

### Build

```bash
docker build -f docker/Dockerfile -t code-metrics-analyzer .
```

### Analyze student projects

**Minimal — only token, GitLab URL, group, and milestones required:**

```bash
docker run --rm \
  -v "$(pwd)/reports:/app/reports" \
  -e GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx \
  -e GITLAB_URL=https://gitlab.example.com \
  -e GITLAB_GROUP_ID=szofttech-ab-2024 \
  code-metrics-analyzer
```

**Full example — all optional overrides included:**

```bash
docker run --rm \
  -v "$(pwd)/reports:/app/reports" \
  -e GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx \
  -e GITLAB_URL=https://gitlab.example.com \
  -e GITLAB_GROUP_ID=42 \
  -e GITLAB_SUBGROUP_ID=99 \
  -e MILESTONE_1="Sprint 1,Sprint1" \
  -e MILESTONE_2="Sprint 2,Sprint2" \
  -e MILESTONE_3="Sprint 3" \
  -e CLONE_DIR=/tmp/repos \
  -e REPORT_OUTPUT=/app/reports \
  code-metrics-analyzer
```

Milestones can alternatively be passed as a single JSON env var:

```bash
-e MILESTONE_KEYWORDS='[["Sprint 1","Sprint1"],["Sprint 2","Sprint2"]]'
```

If you have a `config.yml` with defaults (GitLab URL, group ID, milestones, …)
you can mount it and omit the corresponding env vars:

```bash
docker run --rm \
  -v "$(pwd)/bulk_analyzer/config.yml:/opt/bulk_analyzer/config.yml" \
  -v "$(pwd)/reports:/app/reports" \
  -e GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx \
  code-metrics-analyzer
```

After analysis each project's HTML report is written to
`<REPORT_OUTPUT>/project_<id>/index.html`.  Open `index.html` in a browser to
review diagnostics and the commit-history trend across all analysed milestones.

> **Note:** Unity projects are detected automatically.  A Visual Studio solution
> is generated from the `Assets/` directory using pure Python — no Unity editor
> or license is required.
