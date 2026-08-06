# Code Metrics

Automated analysis of software metrics and complexity in student and
open-source C# projects using static analysis.

It downloads GitLab projects (by group/subgroup), locates milestone commits
(or, optionally, just the latest commit on each default branch), runs a
custom Roslyn-based static analyzer over each one, and produces JSON metrics
plus browsable HTML reports with trend charts across commits.

## Currently implemented metrics

| ID | Metric |
|----|--------|
| CMA0001 | Bumpy Road Code Smell (excessive statement nesting) |
| CMA0002 | Function parameter count |
| CMA0003 | LCOM4 (Lack of Cohesion of Methods) |
| CMA0004 | LCOM5 |
| CMA0005 | Maintainability Index |
| CMA0006 | Cyclomatic Complexity |
| CMA0007 | Class Coupling |

## Tech stack & architecture

Two components, glued together by Docker:

- **[`CodeMetricsAnalyzer/`](CodeMetricsAnalyzer/)** — .NET 8 / Roslyn solution.
  Analyzes a `.sln`/`.csproj` and emits diagnostics (CMA0001–CMA0007), then
  exports XML and an HTML report with historical trend charts. Packaged as a
  `dotnet tool` (`CodeMetricsAnalyzer` command).
- **[`bulk_analyzer/`](bulk_analyzer/)** — Python package. Talks to the
  GitLab API to find student/public projects and milestone commits (fuzzy
  matched by name), clones them, invokes `CodeMetricsAnalyzer` on each, and
  aggregates results. Also supports Unity projects (generates a `.sln` for
  the `Assets/` folder without needing the Unity editor).
- **[`docker/`](docker/)** — bundles both of the above (plus MSBuild, cloc,
  git, mono) into a turnkey image so analysis needs no local toolchain setup.

```
GitLab group/subgroup ──▶ bulk_analyzer (Python) ──▶ CodeMetricsAnalyzer (.NET/Roslyn) ──▶ JSON + HTML reports
```

## Getting started

Pick one of two paths:

### Docker (recommended, no local .NET/Python setup)

```bash
docker build -f docker/Dockerfile -t code-metrics-analyzer .

docker run --rm \
  -v "$(pwd)/reports:/app/reports" \
  -e GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx \
  -e GITLAB_URL=https://gitlab.example.com \
  -e GITLAB_GROUP_ID=szofttech-ab-2024 \
  code-metrics-analyzer
```

Open `reports/project_<id>/index.html` when it's done. Full options
(milestones, Unity licensing, `ANALYSIS_MODE=latest_snapshot`, manual
container invocation) are in [`docs/DOCKER_README.md`](docs/DOCKER_README.md).

### From source (local development)

Requirements: `python3`, `.NET SDK 8.0`, optionally `unity` and `cloc`.

```bash
# 1. Build the analyzer
dotnet build CodeMetricsAnalyzer/CodeMetricsAnalyzer

# 2. Set up the Python environment
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
pip install -r bulk_analyzer/requirements.txt

# 3. Configure
cp bulk_analyzer/config.example.yml bulk_analyzer/config.yml
# edit config.yml: gitlab.url, gitlab.token, gitlab.group_id

# 4. Run
python -m bulk_analyzer.analyzer
```

See [`bulk_analyzer/README.md`](bulk_analyzer/README.md) for the full
Windows/Linux walkthrough, public-project analysis, and the HTML report
generator.

## Usage cheat-sheet

| Task | Command |
|------|---------|
| Analyze a solution directly (.NET tool) | `CodeMetricsAnalyzer analyze YourSolution.sln --report-output ./reports` |
| Analyze GitLab group by milestones | `python -m bulk_analyzer.analyzer` |
| Analyze latest commit on default branch | `python -m bulk_analyzer.latest_snapshot_analyzer --report-output ./reports` |
| Analyze public/open-source repos | `python bulk_analyzer/public_project_analyzer.py` |
| Generate standalone bulk HTML report | `python -m bulk_analyzer.html_report_generator` |
| Build & run turnkey Docker image | `docker build -f docker/Dockerfile -t code-metrics-analyzer .` |
| Run analyzer unit tests | `dotnet test CodeMetricsAnalyzer/CodeMetricsAnalyzer.sln` |

Deeper references:
- [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — CLI options, `appsettings.json` configuration, CI/CD examples (GitLab/GitHub/Azure)
- [`docs/DOCKER_README.md`](docs/DOCKER_README.md) — Docker workflows, Unity licensing, environment variables
- [`.gitlab-ci.example.yml`](.gitlab-ci.example.yml) — copy-paste GitLab CI pipeline template
- [`CodeMetricsAnalyzer/README.md`](CodeMetricsAnalyzer/README.md) — analyzer solution layout
- [`bulk_analyzer/README.md`](bulk_analyzer/README.md) — GitLab downloader/orchestrator details

## Directory structure

```
code-metrics/
├── CodeMetricsAnalyzer/            .NET/Roslyn solution
│   ├── CodeMetricsAnalyzer/            CLI entry point (dotnet tool)
│   ├── CodeMetricsAnalyzer.Analyzers/  Roslyn diagnostic analyzers + config
│   ├── CodeMetricsAnalyzer.Commands/   `analyze` command implementation
│   ├── CodeMetricsAnalyzer.ResultExporter/  XML/HTML report generation
│   └── CodeMetricsAnalyzer.Analyzers.Tests/ Unit tests
├── bulk_analyzer/                  Python package: GitLab downloader + orchestrator
│   └── visualization/                  Jupyter notebooks for exploring results
├── docker/                         Dockerfiles (Linux/Windows/dotnet) + entrypoint
├── docs/                           Deep-dive human docs (quick start, Docker)
├── .claude/                        AI agent memory (see .claude/CLAUDE.md)
├── .gitlab-ci.example.yml          GitLab CI pipeline template
├── LICENSE                         BSD-3-Clause
└── README.md                       this file
```

## License

BSD-3-Clause — see [`LICENSE`](LICENSE).
