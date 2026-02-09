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

## GitLab CI/CD Integration

You can integrate Code Metrics Analyzer into your GitLab CI/CD pipeline to automatically analyze code quality on every commit. The analyzer generates interactive HTML reports with historical tracking.

### Basic GitLab CI Configuration

Create a `.gitlab-ci.yml` file in your repository root:

```yaml
stages:
  - build
  - analyze
  - report

variables:
  DOTNET_VERSION: "8.0"
  ANALYZER_VERSION: "latest"  # Or specify a version tag

build:
  stage: build
  image: mcr.microsoft.com/dotnet/sdk:${DOTNET_VERSION}
  script:
    - dotnet restore
    - dotnet build --no-restore --configuration Release
  artifacts:
    paths:
      - "**/bin/Release/**"
    expire_in: 1 hour

code-metrics:
  stage: analyze
  image: mcr.microsoft.com/dotnet/sdk:${DOTNET_VERSION}
  dependencies:
    - build
  before_script:
    # Install Code Metrics Analyzer
    - dotnet tool install --global CodeMetricsAnalyzer --version ${ANALYZER_VERSION}
    - export PATH="$PATH:$HOME/.dotnet/tools"
  script:
    # Run analysis on your solution
    - CodeMetricsAnalyzer analyze YourSolution.sln --report-output ./metrics-report --history-dir ./metrics-history
  artifacts:
    name: "code-metrics-$CI_COMMIT_SHORT_SHA"
    paths:
      - metrics-report/
      - metrics-history/
    reports:
      # Optional: You can add custom report format here
    expire_in: 30 days
    when: always

# Publish reports to GitLab Pages (optional)
pages:
  stage: report
  dependencies:
    - code-metrics
  script:
    - mkdir -p public
    - cp -r metrics-report/* public/
  artifacts:
    paths:
      - public
  only:
    - main
    - master
```

### Advanced Configuration with Persistent History

For tracking metrics over time across pipeline runs, use GitLab's cache or artifacts from previous jobs:

```yaml
stages:
  - build
  - analyze

variables:
  DOTNET_VERSION: "8.0"
  HISTORY_DIR: "metrics-history"

build:
  stage: build
  image: mcr.microsoft.com/dotnet/sdk:${DOTNET_VERSION}
  script:
    - dotnet restore
    - dotnet build --no-restore --configuration Release
  artifacts:
    paths:
      - "**/bin/Release/**"
    expire_in: 1 hour

code-metrics:
  stage: analyze
  image: mcr.microsoft.com/dotnet/sdk:${DOTNET_VERSION}
  dependencies:
    - build
  before_script:
    - dotenv -c ./your-env-file
    - dotnet tool install --global CodeMetricsAnalyzer
    - export PATH="$PATH:$HOME/.dotnet/tools"
  script:
    # Create history directory if it doesn't exist
    - mkdir -p ${HISTORY_DIR}
    
    # Run analysis with persistent history
    - |
      CodeMetricsAnalyzer analyze YourSolution.sln \
        --report-output ./metrics-report \
        --history-dir ./${HISTORY_DIR}
    
    # Display summary
    - echo "Code Metrics Analysis Complete!"
    - echo "Report available in artifacts"
  
  # Cache history across pipeline runs
  cache:
    key: metrics-history-${CI_COMMIT_REF_SLUG}
    paths:
      - ${HISTORY_DIR}/
    policy: pull-push
  
  artifacts:
    name: "code-metrics-$CI_COMMIT_SHORT_SHA"
    paths:
      - metrics-report/
      - ${HISTORY_DIR}/*.xml
    expire_in: 90 days
    when: always
    expose_as: "Code Metrics Report"
  
  # Allow viewing reports in merge requests
  only:
    - merge_requests
    - main
    - master
    - develop
```

### Multi-Project Analysis

For analyzing multiple projects in a monorepo:

```yaml
code-metrics:
  stage: analyze
  image: mcr.microsoft.com/dotnet/sdk:8.0
  before_script:
    - dotnet tool install --global CodeMetricsAnalyzer
    - export PATH="$PATH:$HOME/.dotnet/tools"
  script:
    # Analyze each project
    - |
      for solution in $(find . -name "*.sln" -not -path "*/bin/*" -not -path "*/obj/*"); do
        echo "Analyzing: $solution"
        project_name=$(basename "$solution" .sln)
        CodeMetricsAnalyzer analyze "$solution" \
          --report-output "./metrics-report/${project_name}" \
          --history-dir "./metrics-history/${project_name}"
      done
  artifacts:
    paths:
      - metrics-report/
      - metrics-history/
    expire_in: 30 days
    when: always
```

### With Quality Gate (Fail on High Issue Count)

```yaml
code-metrics-with-gate:
  stage: analyze
  image: mcr.microsoft.com/dotnet/sdk:8.0
  before_script:
    - dotnet tool install --global CodeMetricsAnalyzer
    - export PATH="$PATH:$HOME/.dotnet/tools"
  script:
    # Run analysis
    - CodeMetricsAnalyzer analyze YourSolution.sln --output metrics.xml --report-output ./metrics-report --history-dir ./metrics-history
    
    # Parse results and check thresholds
    - |
      # Count critical issues (example using xmllint)
      CRITICAL_COUNT=$(xmllint --xpath "count(//Diagnostic[@Severity='Error'])" metrics.xml 2>/dev/null || echo "0")
      echo "Critical issues found: $CRITICAL_COUNT"
      
      # Fail if threshold exceeded
      if [ "$CRITICAL_COUNT" -gt "10" ]; then
        echo "ERROR: Too many critical issues ($CRITICAL_COUNT > 10)"
        exit 1
      fi
  
  artifacts:
    paths:
      - metrics-report/
      - metrics-history/
      - metrics.xml
    expire_in: 30 days
    when: always
  
  allow_failure: false
```

### Viewing Reports

After the pipeline runs:

1. **Artifacts**: Navigate to `CI/CD > Pipelines > [Your Pipeline] > Job Artifacts`
2. **Download** the `metrics-report` folder
3. **Open** `index.html` in your browser to view the interactive report
4. **GitLab Pages**: If configured, reports are available at `https://[username].gitlab.io/[project]`

### Features in the HTML Report

- **Home**: Overview of all projects and issue counts with trend indicators
- **Summary**: Detailed breakdown by issue type
- **History**: 
  - Total issues over time (line chart)
  - Issues by severity (multi-line chart)
  - **Clickable metric buttons**: Click any issue type to see its individual trend
  - Commit history table with changes
- **Project Pages**: File-by-file analysis with code snippets

### Git Information Detection

The analyzer automatically detects Git commit information from the **solution's directory** by walking up the directory tree to find the Git repository root. This means:

- ? **Works in CI/CD**: No need to change directories before running the analyzer
- ? **Flexible execution**: Can run analyzer from any directory
- ? **Nested solutions**: Automatically finds `.git` directory even if solution is in a subdirectory
- ? **Git submodules**: Supports Git submodules and worktrees (detects `.git` file)
- ? **Automatic detection**: Finds commit hash, message, author, and date from the repository
- ?? **Requirement**: The solution directory must be inside a Git repository (anywhere in the directory tree)

**How it works:**
1. Starts from the solution's directory
2. Walks up the directory tree looking for `.git` directory or file
3. Uses the found repository root for all Git operations
4. Falls back to environment variables if Git is not available

**Example repository structures:**
```
# Monorepo with nested solutions
monorepo/
??? .git/
??? backend/
?   ??? Backend.sln        # ? Finds .git in monorepo/
??? frontend/
    ??? Frontend.sln       # ? Finds .git in monorepo/

# Solution in subdirectory
project/
??? .git/
??? docs/
??? src/
    ??? App.sln            # ? Finds .git in project/

# Git submodule
parent/
??? .git/
??? submodule/
    ??? .git               # File pointing to parent
    ??? Module.sln         # ? Finds .git file
```

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

### Troubleshooting

If the analyzer fails to run:

1. Ensure your solution builds successfully in the `build` stage
2. Check that .NET SDK version matches your project's target framework
3. Verify the analyzer tool is installed: `dotnet tool list -g`
4. Enable verbose logging: Add `--verbosity detailed` to the analyze command

### Example Output Structure

```
artifacts/
??? metrics-report/
?   ??? index.html          # Main dashboard
?   ??? summary.html        # Issue summary
?   ??? history.html        # Historical trends (with clickable metrics)
?   ??? project_*.html      # Individual project reports
?   ??? styles.css          # Styling
??? metrics-history/
    ??? metrics_20240115-143022_a1b2c3d4.xml
    ??? metrics_20240116-091534_b2c3d4e5.xml
    ??? ...
```

### Best Practices

1. **Cache History**: Use GitLab cache to persist history across pipeline runs
2. **Regular Cleanup**: Set appropriate `expire_in` for artifacts (30-90 days)
3. **Branch Strategy**: Analyze main branches and merge requests
4. **Quality Gates**: Set thresholds for critical issues
5. **Pages Publishing**: Use GitLab Pages for easy report access
6. **Notifications**: Add notification steps on quality gate failures
