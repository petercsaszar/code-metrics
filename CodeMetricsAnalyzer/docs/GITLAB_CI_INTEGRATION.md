# GitLab CI Integration Guide

This guide explains how to integrate the Code Metrics Analyzer with GitLab CI/CD to automatically analyze your code and track metrics over time.

## Features

- ?? **Automatic Analysis**: Runs on every commit/merge request
- ?? **Historical Tracking**: Maintains history across commits
- ?? **Trend Visualization**: Charts showing metrics over time
- ?? **GitLab Pages**: Optional deployment to view reports in browser
- ?? **Artifact Storage**: Reports saved for 30 days

## Quick Start

### 1. Add `.gitlab-ci.yml` to Your Repository

Copy the provided `.gitlab-ci.yml` file to the root of your repository and update the following:

```yaml
# Replace 'YourSolution.sln' with your actual solution/project file
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze YourSolution.sln --report-output ${ANALYZER_OUTPUT}
```

### 2. Configure GitLab Pages (Optional)

If you want to view reports directly in your browser:

1. Go to **Settings** ? **Pages** in your GitLab project
2. The reports will be available at: `https://yourname.gitlab.io/yourproject/`

### 3. First Run

Commit and push the `.gitlab-ci.yml` file:

```bash
git add .gitlab-ci.yml
git commit -m "Add code metrics analysis CI pipeline"
git push
```

## Pipeline Stages

### 1. Build Stage
- Compiles the CodeMetricsAnalyzer tool
- Creates a publishable artifact
- Runs on: all commits and merge requests

### 2. Analyze Stage
- Restores previous history (if available)
- Runs code metrics analysis
- Generates HTML reports with historical data
- Saves history for next run
- Runs on: all commits and merge requests

### 3. Deploy Stage (Pages)
- Copies reports to `public/` directory
- Deploys to GitLab Pages
- Runs on: main branch only

## Accessing Reports

### Via GitLab Artifacts

1. Go to your pipeline in GitLab
2. Click on the **code-metrics-analysis** job
3. On the right side, click **Browse** under artifacts
4. Navigate to the report files and download or view them

### Via GitLab Pages

If you enabled GitLab Pages deployment:
- Reports are available at: `https://yourname.gitlab.io/yourproject/`
- Automatically updated on every main branch commit

## Historical Data

The pipeline maintains historical metrics across commits:

- **Storage**: `history.json` file stored as a GitLab artifact
- **Retention**: Last 100 commits
- **Visualization**: Charts on the History page show trends over time
- **Comparison**: Index page shows change from previous commit

### How It Works

1. Before analysis, the pipeline checks for `history.json` from previous runs
2. After analysis, the current commit's metrics are added to the history
3. The updated history is saved as an artifact for the next run
4. Charts and trend indicators use this historical data

## Report Structure

```
code-metrics-report/
??? index.html          # Overview with trend indicators
??? summary.html        # Issue breakdown by type
??? history.html        # Historical charts and commit list
??? project_*.html      # Individual project details
??? styles.css          # Stylesheet
??? history.json        # Historical metrics data
```

## Customization

### Analyzing Specific Projects

```yaml
# Analyze a single project
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze MyProject/MyProject.csproj --report-output ${ANALYZER_OUTPUT}
```

### XML Output

```yaml
# Generate both HTML and XML reports
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze YourSolution.sln --output ${ANALYZER_OUTPUT}/results.xml --report-output ${ANALYZER_OUTPUT}
```

### Retention Period

```yaml
artifacts:
  expire_in: 90 days  # Change from default 30 days
```

### Run on Specific Branches

```yaml
only:
  - main
  - develop
  - /^release\/.*$/  # All release branches
```

### Schedule Regular Analysis

In GitLab: **CI/CD** ? **Schedules** ? **New Schedule**

```
Description: Weekly code metrics analysis
Interval Pattern: 0 0 * * 0 (Every Sunday at midnight)
Target Branch: main
```

## Environment Variables

You can configure these in **Settings** ? **CI/CD** ? **Variables**:

| Variable | Description | Default |
|----------|-------------|---------|
| `ANALYZER_OUTPUT` | Output directory for reports | `code-metrics-report` |
| `HISTORY_FILE` | History data file name | `history.json` |
| `DOTNET_VERSION` | .NET SDK version | `8.0` |

## Advanced Scenarios

### Multi-Solution Projects

```yaml
script:
  - dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze Solution1.sln --report-output ${ANALYZER_OUTPUT}/solution1
  - dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze Solution2.sln --report-output ${ANALYZER_OUTPUT}/solution2
```

### Fail Pipeline on Threshold

```yaml
script:
  - dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze YourSolution.sln --report-output ${ANALYZER_OUTPUT}
  - |
    ISSUE_COUNT=$(grep -oP '"TotalIssues":\s*\K\d+' ${ANALYZER_OUTPUT}/history.json | tail -1)
    if [ "$ISSUE_COUNT" -gt 100 ]; then
      echo "Too many issues: $ISSUE_COUNT (threshold: 100)"
      exit 1
    fi
```

### Upload to External Storage

#### AWS S3
```yaml
upload-to-s3:
  stage: deploy
  image: amazon/aws-cli
  dependencies:
    - code-metrics-analysis
  script:
    - aws s3 sync ${ANALYZER_OUTPUT} s3://your-bucket/code-metrics/${CI_COMMIT_SHA}/
  only:
    - main
```

#### Azure Blob Storage
```yaml
upload-to-azure:
  stage: deploy
  image: mcr.microsoft.com/azure-cli
  dependencies:
    - code-metrics-analysis
  script:
    - az storage blob upload-batch -d code-metrics -s ${ANALYZER_OUTPUT}
  only:
    - main
```

## Merge Request Integration

The pipeline automatically runs on merge requests, allowing you to:

1. See code quality trends before merging
2. Compare metrics between branches
3. Make informed decisions about code changes

In the merge request, you'll see:
- Pipeline status
- Link to artifacts (Browse button)
- Ability to download and review reports

## Troubleshooting

### History Not Persisting

**Problem**: Charts always start from scratch

**Solution**: Ensure the `history.json` file is properly preserved:
```yaml
artifacts:
  paths:
    - ${HISTORY_FILE}
  expire_in: 30 days  # Must be long enough for next commit
```

### Reports Not Showing on GitLab Pages

**Problem**: 404 error when accessing pages URL

**Solution**: 
1. Verify `pages` job completed successfully
2. Check that `public/` directory contains `index.html`
3. Wait a few minutes for GitLab to process the deployment

### Build Fails on First Run

**Problem**: Cannot find solution/project file

**Solution**: Update the path in `.gitlab-ci.yml`:
```yaml
# Use relative path from repository root
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze ./src/YourProject.sln --report-output ${ANALYZER_OUTPUT}
```

## Best Practices

1. **Run on Main Branch**: Always analyze main/master branch for consistent history
2. **Regular Schedules**: Set up scheduled pipelines for consistent data points
3. **Review Trends**: Check the History page regularly to identify patterns
4. **Set Thresholds**: Consider failing builds if metrics exceed acceptable levels
5. **Archive Reports**: Export important reports before artifact expiration

## Example Workflow

1. Developer pushes code ? Pipeline runs analysis
2. Merge request shows analysis results
3. Team reviews metrics before merging
4. After merge to main ? History updated with new data point
5. GitLab Pages shows latest report with full history
6. Weekly scheduled run ensures consistent tracking

## Support

For issues or questions:
- Check the pipeline logs for detailed error messages
- Review the generated reports for diagnostic information
- Verify all paths and configuration match your repository structure
