# Code Metrics Analyzer - Quick Start Guide

## Installation

The tool is not currently published to a public NuGet feed — build and install it
locally as a .NET global tool. The command you run *after* install is
`CodeMetricsAnalyzer` (the `ToolCommandName`), but the package id used with
`tool install` is `ELTE.FI.CodeMetricsAnalyzer`.

### From Source (only supported path today)

```bash
cd CodeMetricsAnalyzer/CodeMetricsAnalyzer
dotnet pack --configuration Release
dotnet tool install --global --add-source ./nupkg ELTE.FI.CodeMetricsAnalyzer
```

### If you publish the package to a private/public feed

```bash
dotnet tool install --global ELTE.FI.CodeMetricsAnalyzer
```

## Basic Usage

### Analyze a Solution

```bash
CodeMetricsAnalyzer analyze YourSolution.sln --report-output ./reports
```

### Analyze with History Tracking

```bash
CodeMetricsAnalyzer analyze YourSolution.sln \
  --report-output ./reports \
  --history-dir ./metrics-history
```

### Export to XML

```bash
CodeMetricsAnalyzer analyze YourSolution.sln \
  --output metrics.xml \
  --report-output ./reports
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `source` | Path to .sln or .csproj file | Required |
| `--output` | Output XML file path | None |
| `--report-output` | HTML report folder path | None |
| `--history-dir` | Directory for historical metrics | `<report-output>/history` |
| `--msbuild-path` | Path to MSBuild installation | Auto-detected |

## Understanding the Reports

### Home Page (`index.html`)
- **Summary Cards**: Total issues, projects analyzed, unique issue types
- **Trend Indicator**: Shows increase/decrease since last commit
- **Projects Table**: List of all analyzed projects with issue counts

### Summary Page (`summary.html`)
- **Issue Breakdown**: All issues grouped by type
- **Severity Levels**: Error, Warning, Info classification
- **Counts**: Number of occurrences per issue type

### History Page (`history.html`)
- **Total Issues Chart**: Trend over time
- **Severity Chart**: Errors, warnings, and info over time
- **Issue Type Trends**: Click any metric button to see individual trend
- **Commit History Table**: Detailed view of each analysis run

### Project Pages (`project_*.html`)
- **File-by-File Analysis**: Issues grouped by source file
- **Line Numbers**: Exact location of each issue
- **Code Snippets**: Click "Show Code" to view context

## Supported Metrics

### CMA0001 - Bumpy Road Code Smell
Detects excessive statement nesting in methods, making code harder to read.

**Default Threshold**: `BumpynessThreshold` = 2

### CMA0002 - Function Parameter Count
Flags methods with too many parameters.

**Default Threshold**: `ParameterCountThreshold` = 4

### CMA0003 - LCOM4 (Lack of Cohesion of Methods)
Measures class cohesion based on method/field interactions.

**Default Threshold**: `CohesionThreshold` = 4 components

### CMA0004 - LCOM5
Alternative cohesion metric focusing on member usage.

**Default Threshold**: `CohesionThreshold` = 0.5

### CMA0005 - Maintainability Index
Flags methods with a low maintainability index.

**Default Threshold**: `MinimumMaintainabilityIndex` = 65

### CMA0006 - Cyclomatic Complexity
Flags methods with high cyclomatic complexity.

**Default Threshold**: `MaximumComplexity` = 6

### CMA0007 - Class Coupling
Flags types that depend on too many other types.

**Default Threshold**: `MaximumClassCoupling` = 15

All diagnostics are enabled by default; there is currently no per-analyzer
on/off switch, only threshold tuning via `appsettings.json`.

## Configuration

Create or modify `appsettings.json` next to the analyzer executable (see
[`CodeMetricsAnalyzer/CodeMetricsAnalyzer/appsettings.json`](../CodeMetricsAnalyzer/CodeMetricsAnalyzer/appsettings.json)
for the shipped defaults):

```json
{
  "BumpyRoadAnalysis": {
    "BumpynessThreshold": 2
  },
  "FunctionParameterCountAnalysis": {
    "ParameterCountThreshold": 4
  },
  "LCOM4Analysis": {
    "CohesionThreshold": 4,
    "MinimumMethodCount": 2,
    "MinimumFieldCount": 1
  },
  "LCOM5Analysis": {
    "CohesionThreshold": 0.5,
    "MinimumMethodCount": 2,
    "MinimumFieldCount": 1
  },
  "MaintainabilityIndexAnalysis": {
    "MinimumMaintainabilityIndex": 65
  },
  "CyclomaticComplexityAnalysis": {
    "MaximumComplexity": 6
  },
  "ClassCouplingAnalysis": {
    "MaximumClassCoupling": 15
  }
}
```

## CI/CD Integration

### GitLab CI

See `.gitlab-ci.example.yml` for a complete configuration.

Basic setup:

```yaml
code-metrics:
  stage: analyze
  image: mcr.microsoft.com/dotnet/sdk:8.0
  before_script:
    - dotnet tool install --global CodeMetricsAnalyzer
    - export PATH="$PATH:$HOME/.dotnet/tools"
  script:
    - CodeMetricsAnalyzer analyze YourSolution.sln --report-output ./reports --history-dir ./history
  artifacts:
    paths:
      - reports/
      - history/
    expire_in: 30 days
  cache:
    key: metrics-history
    paths:
      - history/
```

### GitHub Actions

```yaml
- name: Install Code Metrics Analyzer
  run: dotnet tool install --global CodeMetricsAnalyzer

- name: Run Analysis
  run: CodeMetricsAnalyzer analyze YourSolution.sln --report-output ./reports --history-dir ./history

- name: Upload Reports
  uses: actions/upload-artifact@v3
  with:
    name: code-metrics
    path: reports/
```

### Azure DevOps

```yaml
- task: DotNetCoreCLI@2
  displayName: 'Install Code Metrics Analyzer'
  inputs:
    command: custom
    custom: tool
    arguments: 'install --global CodeMetricsAnalyzer'

- task: DotNetCoreCLI@2
  displayName: 'Run Code Metrics Analysis'
  inputs:
    command: custom
    custom: CodeMetricsAnalyzer
    arguments: 'analyze $(Build.SourcesDirectory)/YourSolution.sln --report-output $(Build.ArtifactStagingDirectory)/reports'

- task: PublishBuildArtifacts@1
  displayName: 'Publish Metrics Report'
  inputs:
    pathToPublish: '$(Build.ArtifactStagingDirectory)/reports'
    artifactName: 'code-metrics'
```

## Historical Tracking

The analyzer automatically tracks metrics over time when `--history-dir` is specified:

1. **First Run**: Creates initial baseline
2. **Subsequent Runs**: Generates new XML file and updates trends
3. **File Format**: `metrics_YYYYMMDD-HHMMSS_<commit-hash>.xml`
4. **Retention**: Keeps last 100 metrics automatically

### History Files Location

```
history/
├── metrics_20240115-143022_a1b2c3d4.xml
├── metrics_20240116-091534_b2c3d4e5.xml
├── metrics_20240117-154821_c3d4e5f6.xml
└── ...
```

### Viewing Historical Trends

1. Open `history.html` in the report
2. Scroll to "Issue Type Trends"
3. Click any metric button (e.g., "CMA0001")
4. View the individual trend chart for that metric

## Troubleshooting

### "No projects found"
- Verify the solution file path
- Ensure the solution builds successfully: `dotnet build YourSolution.sln`

### "MSBuild not found"
- Install .NET SDK 8.0 or later
- Or specify MSBuild path: `--msbuild-path "C:\Program Files\Microsoft Visual Studio\..."`

### History not appearing
- Ensure `--history-dir` is specified
- Check that directory has write permissions
- Verify Git is initialized (commit hash is used in filenames)

### Reports show "unknown" for git info
- Run in a Git repository
- Or set environment variables:
  - `CI_COMMIT_SHA`: Commit hash
  - `CI_COMMIT_MESSAGE`: Commit message
  - `CI_COMMIT_AUTHOR`: Author name

## Examples

### Analyze and Generate Reports

```bash
# Basic analysis with HTML report
CodeMetricsAnalyzer analyze MySolution.sln --report-output ./reports

# With history tracking
CodeMetricsAnalyzer analyze MySolution.sln \
  --report-output ./reports \
  --history-dir ./metrics-history

# Export XML for processing
CodeMetricsAnalyzer analyze MySolution.sln \
  --output metrics.xml

# All together
CodeMetricsAnalyzer analyze MySolution.sln \
  --output metrics.xml \
  --report-output ./reports \
  --history-dir ./shared-history
```

### CI/CD with Persistent History

```bash
# In CI script
mkdir -p /shared/metrics-history
CodeMetricsAnalyzer analyze ${SOLUTION_FILE} \
  --report-output ./reports \
  --history-dir /shared/metrics-history
```

### Multi-Project Analysis

```bash
# Analyze all solutions in repository
for sln in $(find . -name "*.sln"); do
  project_name=$(basename "$sln" .sln)
  CodeMetricsAnalyzer analyze "$sln" \
    --report-output "./reports/${project_name}" \
    --history-dir "./history/${project_name}"
done
```

## Best Practices

1. **Consistent History Location**: Use the same `--history-dir` across runs
2. **Regular Cleanup**: Keep artifacts for 30-90 days
3. **Quality Gates**: Set thresholds for critical issues
4. **Branch Strategy**: Analyze main branches and pull requests
5. **Automated Reports**: Publish to pages/artifacts for easy access
6. **Trend Monitoring**: Regularly review the History page for patterns
7. **Team Communication**: Share reports with development team

## Getting Help

- **Documentation**: See the [root README](../README.md)
- **Issues**: Report bugs and feature requests on the project repository
- **Configuration**: Check `appsettings.json` for available options

## Version Information

Check installed version:

```bash
dotnet tool list -g | grep CodeMetricsAnalyzer
```

Update to latest:

```bash
dotnet tool update --global CodeMetricsAnalyzer
```
