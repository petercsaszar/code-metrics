# TicTacToeGame - Code Metrics Integration Guide

## Overview

The Code Metrics Analyzer has been integrated into your TicTacToeGame project's GitLab CI pipeline, similar to how ReportGenerator is used for code coverage.

## Pipeline Structure

Your CI/CD pipeline now includes these stages:

```
1. Build    ? Compile models, views, and analyzer tool
2. Test     ? Run unit tests with coverage (ReportGenerator)
3. Analyze  ? Run code metrics analysis
4. Deploy   ? Publish to GitLab Pages (coverage + metrics + docs)
```

## What Was Added

### New Pipeline Job: `build_analyzer`

**Stage**: `build`  
**Purpose**: Builds the Code Metrics Analyzer tool  
**Output**: Published tool in `./analyzer-tool/`  
**Artifacts**: Tool binaries (expires in 1 hour)

```yaml
build_analyzer:
  stage: build
  script:
    - dotnet build CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj -c Release
    - dotnet publish CodeMetricsAnalyzer/CodeMetricsAnalyzer.csproj -c Release -o ./analyzer-tool
```

### New Pipeline Job: `code_metrics`

**Stage**: `analyze` (new stage)  
**Purpose**: Analyzes TicTacToeGame.sln for code quality metrics  
**Dependencies**: Requires `build_analyzer` job  
**Features**:
- Historical tracking across commits
- XML and HTML report generation
- Automatic history preservation
- Issue count extraction

```yaml
code_metrics:
  stage: analyze
  script:
    - dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze TicTacToeGame.sln --report-output ${ANALYZER_OUTPUT}
```

### Updated: `pages` Job

The GitLab Pages deployment now includes **three** components:

1. **Documentation** (`/docs/`) - Doxygen-generated code documentation
2. **Coverage** (`/coverage/`) - Code coverage from ReportGenerator  
3. **Metrics** (`/metrics/`) - Code metrics reports (**NEW**)

## GitLab Pages Structure

After deployment, your GitLab Pages will be organized like this:

```
https://yourname.gitlab.io/tictactoegame/
??? docs/           # Code documentation (Doxygen)
??? coverage/       # Test coverage (ReportGenerator)
??? metrics/        # Code metrics (CodeMetricsAnalyzer)
    ??? index.html      # Main metrics overview
    ??? summary.html    # Issue summary
    ??? history.html    # Historical trends & charts
    ??? project_*.html  # Per-project details
    ??? history.json    # Historical data
```

## Features

### 1. Historical Tracking

Just like code coverage trends, code metrics are now tracked over time:

- **Stored**: `history.json` (cached between pipeline runs)
- **Retention**: Last 100 commits
- **Metrics Tracked**:
  - Total issues per commit
  - Issues by type (CM001, CM002, etc.)
  - Issues by severity (Error, Warning, Info)
  - Commit metadata (hash, message, author, date)

### 2. Trend Visualization

View interactive charts on the History page:

- **Total Issues Chart**: See issue count progression
- **Severity Breakdown**: Compare Errors, Warnings, and Info over time
- **Commit Table**: Full history with change indicators (? ? ?)

### 3. Comparison with ReportGenerator

| Feature | ReportGenerator (Coverage) | CodeMetricsAnalyzer (Metrics) |
|---------|---------------------------|-------------------------------|
| **Purpose** | Test coverage | Code quality metrics |
| **Input** | Cobertura XML | Source code |
| **Output** | HTML + Cobertura | HTML + XML |
| **Charts** | ? Coverage trends | ? Metrics trends |
| **GitLab Pages** | ? `/coverage/` | ? `/metrics/` |
| **History** | Per-pipeline | Per-commit (cached) |
| **CI Integration** | `test_model` job | `code_metrics` job |

## Using the Reports

### View in Browser (GitLab Pages)

1. Navigate to: `https://yourname.gitlab.io/tictactoegame/metrics/`
2. Explore:
   - **Home**: Overview with trend from last commit
   - **Summary**: All issue types grouped
   - **History**: Charts and commit timeline
   - **Projects**: Detailed issues per project with code snippets

### View in Pipeline Artifacts

1. Go to **CI/CD** ? **Pipelines**
2. Click on latest pipeline
3. Click **Browse** on `code_metrics` job
4. Navigate to `code-metrics-report/`
5. Download or view reports

### View XML in GitLab UI

The XML output can be used for programmatic analysis:

```bash
# Download from artifacts
curl -o metrics.xml "https://gitlab.com/api/v4/projects/PROJECT_ID/jobs/JOB_ID/artifacts/code-metrics-report/metrics.xml"
```

## Interpreting Results

### Issue Counts

Similar to how you monitor code coverage percentage:

```yaml
# Code Coverage (from test_model job)
TOTAL_COVERAGE=85.50%

# Code Metrics (from code_metrics job)
TOTAL_CODE_METRICS_ISSUES=42
```

Lower issue count = Better code quality (like higher coverage = better testing)

### Trend Indicators

On the index page, you'll see indicators like:

- ?? **? 5 issues decreased** - Good! Code quality improved
- ?? **? 8 issues increased** - Review: New code may need attention
- ?? **? No change** - Stable code quality

### Severity Levels

- **Error** ??: Critical issues requiring immediate attention
- **Warning** ??: Important issues to address soon
- **Info** ??: Suggestions for improvement

## Caching Strategy

The pipeline uses two caching strategies:

### 1. NuGet Packages (existing)

```yaml
cache:
  key: "unittest-$CI_COMMIT_REF_SLUG"
  paths:
    - .nuget
```

### 2. Code Metrics History (new)

```yaml
cache:
  key: "code-metrics-$CI_COMMIT_REF_SLUG"
  paths:
    - ${HISTORY_FILE}
```

This ensures:
- Each branch has its own metrics history
- History survives between pipeline runs
- Trends are preserved even if artifacts expire

## Example Workflow

### Week 1: Baseline
```
Commit: Initial implementation
Issues: 50
Coverage: 80%
```

### Week 2: Feature Development
```
Commit: Add new game modes
Issues: 65 (? 15) - New code added
Coverage: 78% (? 2%) - Coverage temporarily decreased
```

### Week 3: Refactoring
```
Commit: Refactor game logic
Issues: 45 (? 20) - Improved code quality
Coverage: 85% (? 7%) - Better tests
```

### Week 4: Polish
```
Commit: Code cleanup
Issues: 30 (? 15) - Further improvements
Coverage: 88% (? 3%) - Even better tests
```

## Customization

### Analyze Specific Projects Only

Instead of the entire solution:

```yaml
script:
  # Analyze only model projects
  - dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze TicTacToeGame.Model.Basic/TicTacToeGame.Model.Basic.csproj --report-output ${ANALYZER_OUTPUT}
```

### Change History Retention

Default: 100 commits  
To change: Edit `HtmlReportGenerator.cs` line ~70

```csharp
.Take(100)  // Change to 50, 200, etc.
```

### Fail Pipeline on Threshold

Add to `code_metrics` job:

```yaml
script:
  # ... existing analysis commands ...
  
  # Fail if issues exceed threshold
  - |
    ISSUE_COUNT=$(jq '.Metrics[-1].TotalIssues' ${ANALYZER_OUTPUT}/history.json)
    if [ "$ISSUE_COUNT" -gt 50 ]; then
      echo "Too many issues: $ISSUE_COUNT (threshold: 50)"
      exit 1
    fi
```

### Run Only on Master/Main

```yaml
code_metrics:
  # ... existing config ...
  only:
    - master
```

## Troubleshooting

### Analyzer Tool Not Found

**Error**: `dotnet analyzer-tool/CodeMetricsAnalyzer.dll: No such file`

**Solution**: 
- Check `build_analyzer` job succeeded
- Verify `dependencies: [build_analyzer]` in `code_metrics` job

### History Not Accumulating

**Error**: Charts only show one data point

**Solution**:
- Check cache is enabled for `code-metrics-$CI_COMMIT_REF_SLUG`
- Verify `after_script` runs (copies history.json)
- Ensure same branch is being committed to

### GitLab Pages Not Updating

**Error**: Metrics not showing on Pages

**Solution**:
- Check `pages` job succeeded
- Verify running on `master` branch (only branch for Pages)
- Add `code_metrics` to `dependencies` in `pages` job

### XML Report Not Found

**Error**: `junit: ${ANALYZER_OUTPUT}/results.xml` file not found

**Solution**:
This is expected - the XML report is optional. Remove or comment out:

```yaml
reports:
  # junit: ${ANALYZER_OUTPUT}/metrics.xml  # Optional, comment if not needed
```

## Benefits

### Similar to Code Coverage

Just as code coverage helps you:
- ? Identify untested code
- ? Track testing progress
- ? Enforce quality standards

Code metrics help you:
- ? Identify complex code
- ? Track code quality trends
- ? Enforce maintainability standards

### Continuous Monitoring

Both are monitored continuously through CI:
- **Coverage**: After every test run
- **Metrics**: After every commit

Both are visualized:
- **Coverage**: ReportGenerator HTML + GitLab badge
- **Metrics**: Interactive charts + GitLab Pages

## Next Steps

1. ? **Pipeline is configured** - Automatically runs on every commit
2. ? **Reports are published** - Available on GitLab Pages
3. ? **History is tracked** - Trends accumulate over time

### Recommended Actions

1. **Review First Report**: Check `metrics/` on GitLab Pages
2. **Set Baselines**: Note initial issue counts
3. **Monitor Trends**: Review history page weekly
4. **Set Goals**: Aim to reduce issue counts over time
5. **Integrate with Process**: Review metrics in code reviews

## Summary

Your TicTacToeGame project now has comprehensive quality monitoring:

- **Code Coverage** (via ReportGenerator) ? How well is code tested?
- **Code Metrics** (via CodeMetricsAnalyzer) ? How maintainable is code?
- **Documentation** (via Doxygen) ? How well is code documented?

All three are:
- ? Automatically generated on every commit
- ? Published to GitLab Pages
- ? Tracked over time with trends
- ? Available in CI artifacts

Happy analyzing! ??
