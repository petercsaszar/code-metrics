# Code Metrics Analyzer - GitLab CI Quick Start

## ?? Features Overview

Your Code Metrics Analyzer now includes:

1. **?? Interactive HTML Reports** with code snippets
2. **?? Historical Tracking** across commits  
3. **?? GitLab CI Integration** for automated analysis
4. **?? Trend Charts** showing metrics over time
5. **?? GitLab Pages Support** for easy viewing

## ?? What's New

### Historical Metrics
- Tracks up to 100 commits
- Shows trend indicators (? ? ?)
- Compares current vs previous commit
- Stores data in `history.json`

### Charts & Visualization
- Line chart for total issues over time
- Multi-line chart for severity breakdown (Errors, Warnings, Info)
- Interactive charts using Chart.js
- Commit history table with changes

### GitLab CI Pipeline
- **Build stage**: Compiles the analyzer
- **Analyze stage**: Runs analysis and tracks history
- **Deploy stage**: Publishes to GitLab Pages

## ?? Quick Setup

### Step 1: Add GitLab CI Configuration

1. Copy `.gitlab-ci.yml` to your repository root
2. Update the solution/project path:

```yaml
# Line ~40 in .gitlab-ci.yml
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze YOUR_SOLUTION.sln --report-output ${ANALYZER_OUTPUT}
```

3. Commit and push:

```bash
git add .gitlab-ci.yml
git commit -m "Add code metrics CI pipeline"
git push
```

### Step 2: First Run

The first time the pipeline runs:
- ? Builds the analyzer
- ? Analyzes your code
- ? Creates `history.json` with first data point
- ? Generates HTML report
- ? Deploys to GitLab Pages (if on main branch)

### Step 3: View Reports

**Option A: Via GitLab Artifacts**
1. Go to CI/CD ? Pipelines
2. Click on the latest pipeline
3. Click the **Browse** button on the analyze job
4. Open `index.html` in the file browser

**Option B: Via GitLab Pages**
1. Wait for the `pages` job to complete
2. Go to Settings ? Pages
3. Click your pages URL: `https://yourname.gitlab.io/yourproject/`

### Step 4: Subsequent Runs

On every new commit:
- Historical data accumulates
- Charts show trends
- Index page displays change from previous commit
- Reports become more insightful over time

## ?? Report Pages

### Home (index.html)
- Summary cards (total issues, projects, issue types)
- **Trend indicator** showing change from last commit
- Project list with issue counts

### Summary (summary.html)
- All issue types grouped
- Sorted by frequency
- Severity indicators

### History (history.html) **[NEW]**
- **Line chart**: Total issues over time
- **Multi-line chart**: Issues by severity
- **Commit table**: Full history with changes
- Commit hash, message, author, and timestamp

### Project Details (project_*.html)
- Issues grouped by file
- **Code snippets** (click "Show Code")
- Line numbers and locations

## ?? Configuration Options

### Analyze Different Projects

```yaml
# Single project
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze MyProject.csproj --report-output ${ANALYZER_OUTPUT}

# Multiple solutions
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze Solution1.sln --report-output ${ANALYZER_OUTPUT}/sol1
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze Solution2.sln --report-output ${ANALYZER_OUTPUT}/sol2
```

### XML + HTML Output

```yaml
- dotnet analyzer-tool/CodeMetricsAnalyzer.dll analyze YourSolution.sln \
    --output ${ANALYZER_OUTPUT}/results.xml \
    --report-output ${ANALYZER_OUTPUT}
```

### Change History Retention

Edit `HtmlReportGenerator.cs`:

```csharp
// Line ~70
.Take(100)  // Change to 50, 200, etc.
```

### Run on Specific Branches

```yaml
only:
  - main
  - develop
  - /^release\/.*$/
```

### Schedule Regular Analysis

1. GitLab ? CI/CD ? Schedules
2. New Schedule
3. Interval: `0 0 * * 0` (weekly)
4. Target: main

## ?? Understanding the Charts

### Total Issues Chart
- **Blue line**: Total diagnostic count
- **X-axis**: Commit date/time
- **Y-axis**: Issue count
- **Trend**: See if issues are increasing or decreasing

### Severity Chart
- **Red line**: Errors
- **Orange line**: Warnings
- **Blue line**: Info
- Compare relative severity distribution over time

### Commit History Table
Shows for each commit:
- Date and time
- Short hash + message
- Author
- Total issues
- **Change column**: ? increase, ? decrease, ? no change

## ?? Customizing Reports

### Change Colors

Edit the CSS in `HtmlReportGenerator.cs` (GenerateStylesAsync method):

```css
/* Gradient cards */
.card {
    background: linear-gradient(135deg, YOUR_COLOR_1 0%, YOUR_COLOR_2 100%);
}

/* Charts can be customized in GetChartJavaScript */
borderColor: '#YOUR_COLOR',
```

### Add More Metrics

1. Update `HistoricalMetricsDto` to include new metrics
2. Collect data in `LoadAndUpdateHistoricalDataAsync`
3. Add new chart in `GenerateHistoryPageAsync`
4. Implement chart JavaScript in `GetChartJavaScript`

## ?? Troubleshooting

### History Not Accumulating

**Problem**: Charts only show one data point

**Solution**: 
- Check artifact expiration (must be > time between commits)
- Verify `history.json` is in artifacts path
- Ensure `after_script` runs even if analysis fails

### Chart Not Rendering

**Problem**: Blank chart area

**Solution**:
- Check browser console for JavaScript errors
- Verify Chart.js CDN is accessible
- Ensure historical data has valid date formats

### GitLab Pages 404

**Problem**: Pages URL returns 404

**Solution**:
- Wait 5-10 minutes after first deployment
- Verify `pages` job succeeded
- Check `public/index.html` exists in artifacts
- Ensure running on `main` branch (or configure otherwise)

### Analyzer Tool Not Found

**Problem**: `dotnet analyzer-tool/CodeMetricsAnalyzer.dll: No such file`

**Solution**:
- Verify `build-analyzer` job succeeded
- Check artifacts were passed via `dependencies`
- Ensure publish path matches: `-o ./analyzer-tool`

## ?? Best Practices

1. **Commit Regularly**: More data points = better trends
2. **Review History**: Check weekly for patterns
3. **Set Goals**: Use trends to set reduction targets
4. **Document Changes**: Add comments when metrics improve/worsen
5. **Share Reports**: Link team members to GitLab Pages
6. **Archive Important Milestones**: Download reports before artifact expiration

## ?? Example Workflow

```
Week 1: Initial setup ? Baseline established (50 issues)
Week 2: Feature work ? Issues increase to 65 (? 15)
Week 3: Code cleanup ? Issues decrease to 45 (? 20)
Week 4: Refactoring ? Issues decrease to 30 (? 15)
```

Charts clearly show the impact of your refactoring efforts!

## ?? Additional Resources

- **Full GitLab CI Guide**: See `GITLAB_CI_INTEGRATION.md`
- **Report Features**: See `HTML_REPORT_FEATURES.md`
- **GitLab CI Docs**: https://docs.gitlab.com/ee/ci/
- **Chart.js Docs**: https://www.chartjs.org/docs/

## ?? Summary

You now have a complete CI/CD pipeline that:
- ? Automatically analyzes code on every commit
- ? Tracks metrics historically
- ? Generates beautiful reports with charts
- ? Shows code snippets for each issue
- ? Deploys to GitLab Pages for easy access
- ? Provides trend indicators and comparisons

Happy analyzing! ??
