# Metrics analyzer and report generator

.NET/Roslyn solution that statically analyzes C# solutions for code-quality
metrics and produces XML + HTML reports. See [`../docs/QUICKSTART.md`](../docs/QUICKSTART.md)
for CLI usage, configuration, and CI integration examples.

## Projects in this solution
- `CodeMetricsAnalyzer.Analyzers` – the Roslyn diagnostic analyzers and their configuration
- `CodeMetricsAnalyzer.Commands` – the `analyze` CLI command implementation
- `CodeMetricsAnalyzer.ResultExporter` – XML export and HTML report generation
- `CodeMetricsAnalyzer` – the CLI entry point, packaged as the `CodeMetricsAnalyzer` dotnet tool
- `CodeMetricsAnalyzer.Analyzers.Tests` – unit tests for the analyzers

## Currently implemented metrics
- CMA0001 – Bumpy Road Code Smell
- CMA0002 – Function parameter count
- CMA0003 – LCOM4 (Lack of Cohesion of Methods)
- CMA0004 – LCOM5
- CMA0005 – Maintainability Index
- CMA0006 – Cyclomatic Complexity
- CMA0007 – Class Coupling

## Features in the HTML Report

- **Home**: Overview of all projects and issue counts with trend indicators
- **Summary**: Detailed breakdown by issue type
- **History**: 
  - Total issues over time (line chart)
  - Issues by severity (multi-line chart)
  - **Clickable metric buttons**: Click any issue type to see its individual trend
  - Commit history table with changes
- **Project Pages**: File-by-file analysis with code snippets

If Git is not available or the solution is not in a Git repo, the analyzer falls back to environment variables:
- `CI_COMMIT_SHA` - Commit hash
- `CI_COMMIT_MESSAGE` - Commit message  
- `CI_COMMIT_AUTHOR` - Author name

These are automatically set by most CI/CD systems (GitLab CI, GitHub Actions, Azure DevOps, etc.).

### Historical Data

The analyzer stores historical metrics as individual XML files in the `--history-dir`:
- Files are named: `metrics_YYYYMMDD-HHMMSS_<commit-hash>.xml`
- Up to 100 most recent metrics are kept
- Enables trend analysis across commits
- Persists via GitLab cache or artifacts

### Environment Variables

You can customize the analysis using environment variables in your CI:

```yaml
variables:
  ANALYZER_VERSION: "1.0.0"
  HISTORY_DIR: "./metrics-history"
  REPORT_DIR: "./metrics-report"
  MAX_ISSUES_ALLOWED: "50"
```