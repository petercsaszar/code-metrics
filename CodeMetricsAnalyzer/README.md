# Metrics analyzer and report generator

## Currently implemented metrics
- Bumpy Road Code Smell
- Function parameter count
- LCOM4 metrics
- LCOM5 metrics

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