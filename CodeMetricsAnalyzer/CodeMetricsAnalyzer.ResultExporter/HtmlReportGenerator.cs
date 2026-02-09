using CodeMetricsAnalyzer.ResultExporter.DTOs;
using System.Text;

namespace CodeMetricsAnalyzer.ResultExporter;

public class HtmlReportGenerator
{
    private readonly GitInfoProvider _gitInfoProvider = new();
    
    public async Task GenerateReportAsync(string outputPath, ResultExporterArguments arguments, string? historyDirectory = null, CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(outputPath);
        
        var historicalData = await LoadAndUpdateHistoricalDataAsync(outputPath, arguments, historyDirectory, cancellationToken);
        
        await GenerateIndexPageAsync(outputPath, arguments, historicalData, cancellationToken);
        await GenerateSummaryPageAsync(outputPath, arguments, cancellationToken);
        await GenerateHistoryPageAsync(outputPath, historicalData, cancellationToken);
        
        foreach (var project in arguments.ProjectDiagnostics)
        {
            await GenerateProjectPageAsync(outputPath, project, arguments, cancellationToken);
        }
        
        await GenerateStylesAsync(outputPath, cancellationToken);
    }

    private async Task<HistoricalDataCollection> LoadAndUpdateHistoricalDataAsync(string outputPath, ResultExporterArguments arguments, string? historyDirectory, CancellationToken cancellationToken)
    {
        // Use provided history directory or fall back to output directory
        var effectiveHistoryDir = historyDirectory ?? outputPath;
        
        HistoricalDataCollection historicalData;
        
        // Load from history directory if it exists and has XML files
        if (Directory.Exists(effectiveHistoryDir) && Directory.GetFiles(effectiveHistoryDir, "*.xml").Any())
        {
            historicalData = HistoricalDataCollection.LoadFromDirectory(effectiveHistoryDir);
        }
        else
        {
            // Fall back to legacy JSON file for backward compatibility
            var historyFile = Path.Combine(outputPath, "history.json");
            historicalData = await HistoricalDataCollection.LoadAsync(historyFile, cancellationToken);
        }
        
        // Get Git info from solution directory
        var gitInfo = await _gitInfoProvider.GetCurrentGitInfoAsync(arguments.SolutionDirectory, cancellationToken);
        
        var totalIssues = arguments.ProjectDiagnostics.Sum(p => p.Diagnostics.Count);
        var issuesByType = arguments.ProjectDiagnostics
            .SelectMany(p => p.Diagnostics)
            .GroupBy(d => d.Id)
            .ToDictionary(g => g.Key, g => g.Count());
        var issuesBySeverity = arguments.ProjectDiagnostics
            .SelectMany(p => p.Diagnostics)
            .GroupBy(d => d.Severity)
            .ToDictionary(g => g.Key, g => g.Count());
        var issueTypeTitles = arguments.ProjectDiagnostics
            .SelectMany(p => p.Diagnostics)
            .GroupBy(d => d.Id)
            .ToDictionary(g => g.Key, g => g.First().Title);
        
        var newMetric = new HistoricalMetricsDto
        {
            CommitHash = gitInfo.CommitHash,
            CommitMessage = gitInfo.CommitMessage,
            CommitAuthor = gitInfo.CommitAuthor,
            CommitDate = gitInfo.CommitDate,
            TotalIssues = totalIssues,
            ProjectCount = arguments.ProjectDiagnostics.Count,
            UniqueIssueTypes = issuesByType.Count,
            IssuesByType = issuesByType,
            IssuesBySeverity = issuesBySeverity,
            IssueTypeTitles = issueTypeTitles
        };
        
        // Remove existing metric with same commit hash and delete its XML file
        var existingMetric = historicalData.Metrics.FirstOrDefault(m => m.CommitHash == gitInfo.CommitHash);
        if (existingMetric != null)
        {
            historicalData.Metrics.Remove(existingMetric);
            
            // Delete the old XML file if using history directory
            if (historyDirectory != null)
            {
                DeleteOldMetricFile(historyDirectory, existingMetric);
            }
        }
        
        historicalData.Metrics.Add(newMetric);
        
        // Sort and limit to 100 most recent metrics
        historicalData.Metrics = historicalData.Metrics
            .OrderByDescending(m => m.CommitDate)
            .Take(100)
            .ToList();
        
        // Save to history directory if specified
        if (historyDirectory != null)
        {
            Directory.CreateDirectory(historyDirectory);
            
            // Generate filename with timestamp and commit hash
            var timestamp = gitInfo.CommitDate.ToString("yyyyMMdd-HHmmss");
            var shortHash = gitInfo.CommitHash.Length > 8 ? gitInfo.CommitHash.Substring(0, 8) : gitInfo.CommitHash;
            var fileName = $"metrics_{timestamp}_{shortHash}.xml";
            var xmlFilePath = Path.Combine(historyDirectory, fileName);
            
            // Save the new metric file
            await newMetric.SaveAsXmlAsync(xmlFilePath, cancellationToken);
            
            // Clean up old XML files if we have more than 100
            CleanupOldHistoryFiles(historyDirectory, historicalData.Metrics);
        }
        else
        {
            // Fall back to legacy JSON file
            var historyFile = Path.Combine(outputPath, "history.json");
            await historicalData.SaveAsync(historyFile, cancellationToken);
        }
        
        return historicalData;
    }
    
    private void DeleteOldMetricFile(string historyDirectory, HistoricalMetricsDto metric)
    {
        try
        {
            // Generate the filename that would have been used for this metric
            var timestamp = metric.CommitDate.ToString("yyyyMMdd-HHmmss");
            var shortHash = metric.CommitHash.Length > 8 ? metric.CommitHash.Substring(0, 8) : metric.CommitHash;
            var fileName = $"metrics_{timestamp}_{shortHash}.xml";
            var filePath = Path.Combine(historyDirectory, fileName);
            
            if (File.Exists(filePath))
            {
                File.Delete(filePath);
            }
        }
        catch
        {
            // Ignore deletion errors - file might not exist or might be in use
        }
    }
    
    private void CleanupOldHistoryFiles(string historyDirectory, List<HistoricalMetricsDto> currentMetrics)
    {
        try
        {
            // Get all XML files in the history directory
            var allXmlFiles = Directory.GetFiles(historyDirectory, "metrics_*.xml");
            
            // Create a set of valid file names based on current metrics
            var validFileNames = new HashSet<string>(currentMetrics.Select(m =>
            {
                var timestamp = m.CommitDate.ToString("yyyyMMdd-HHmmss");
                var shortHash = m.CommitHash.Length > 8 ? m.CommitHash.Substring(0, 8) : m.CommitHash;
                return $"metrics_{timestamp}_{shortHash}.xml";
            }));
            
            // Delete files that are not in the current metrics list
            foreach (var file in allXmlFiles)
            {
                var fileName = Path.GetFileName(file);
                if (!validFileNames.Contains(fileName))
                {
                    try
                    {
                        File.Delete(file);
                    }
                    catch
                    {
                        // Ignore deletion errors for individual files
                    }
                }
            }
        }
        catch
        {
            // Ignore cleanup errors - not critical
        }
    }

    private async Task GenerateIndexPageAsync(string outputPath, ResultExporterArguments arguments, HistoricalDataCollection historicalData, CancellationToken cancellationToken)
    {
        var totalDiagnostics = arguments.ProjectDiagnostics.Sum(p => p.Diagnostics.Count);
        var projectCount = arguments.ProjectDiagnostics.Count;
        var uniqueIssueTypes = arguments.ProjectDiagnostics
            .SelectMany(p => p.Diagnostics)
            .Select(d => d.Id)
            .Distinct()
            .Count();

        var html = new StringBuilder();
        html.AppendLine(GetHtmlHeader("Code Metrics Analysis Report"));
        html.AppendLine("<body>");
        html.AppendLine(GetNavigation("index"));
        html.AppendLine("<div class=\"container\">");
        html.AppendLine("<h1>Code Metrics Analysis Report</h1>");
        html.AppendLine($"<p class=\"timestamp\">Generated on {DateTime.Now:yyyy-MM-dd HH:mm:ss}</p>");
        
        if (historicalData.Metrics.Count > 1)
        {
            var previous = historicalData.Metrics.OrderByDescending(m => m.CommitDate).Skip(1).FirstOrDefault();
            var current = historicalData.Metrics.OrderByDescending(m => m.CommitDate).First();
            
            if (previous != null)
            {
                var issueChange = current.TotalIssues - previous.TotalIssues;
                var changeClass = issueChange > 0 ? "trend-negative" : issueChange < 0 ? "trend-positive" : "trend-neutral";
                var changeIcon = issueChange > 0 ? "?" : issueChange < 0 ? "?" : "?";
                
                html.AppendLine($"<div class=\"trend-indicator {changeClass}\">");
                html.AppendLine($"<span class=\"trend-icon\">{changeIcon}</span> ");
                html.AppendLine($"{Math.Abs(issueChange)} issue{(Math.Abs(issueChange) != 1 ? "s" : "")} ");
                html.AppendLine(issueChange > 0 ? "increased" : issueChange < 0 ? "decreased" : "no change");
                html.AppendLine(" since last commit");
                html.AppendLine("</div>");
            }
        }
        
        html.AppendLine("<div class=\"summary-cards\">");
        html.AppendLine($"<div class=\"card\"><h3>{totalDiagnostics}</h3><p>Total Issues</p></div>");
        html.AppendLine($"<div class=\"card\"><h3>{projectCount}</h3><p>Projects Analyzed</p></div>");
        html.AppendLine($"<div class=\"card\"><h3>{uniqueIssueTypes}</h3><p>Issue Types</p></div>");
        html.AppendLine("</div>");

        html.AppendLine("<h2>Projects</h2>");
        html.AppendLine("<table>");
        html.AppendLine("<thead><tr><th>Project Name</th><th>Issues</th><th>Details</th></tr></thead>");
        html.AppendLine("<tbody>");
        
        foreach (var project in arguments.ProjectDiagnostics.OrderBy(p => p.Name))
        {
            var projectFileName = GetSafeFileName(project.Name);
            html.AppendLine($"<tr>");
            html.AppendLine($"<td>{EscapeHtml(project.Name)}</td>");
            html.AppendLine($"<td><span class=\"badge badge-{GetSeverityClass(project.Diagnostics.Count)}\">{project.Diagnostics.Count}</span></td>");
            html.AppendLine($"<td><a href=\"project_{projectFileName}.html\">View Details</a></td>");
            html.AppendLine("</tr>");
        }
        
        html.AppendLine("</tbody>");
        html.AppendLine("</table>");
        html.AppendLine("</div>");
        html.AppendLine("</body>");
        html.AppendLine("</html>");

        await File.WriteAllTextAsync(Path.Combine(outputPath, "index.html"), html.ToString(), cancellationToken);
    }

    private async Task GenerateSummaryPageAsync(string outputPath, ResultExporterArguments arguments, CancellationToken cancellationToken)
    {
        var diagnosticGroups = arguments.ProjectDiagnostics
            .SelectMany(p => p.Diagnostics)
            .GroupBy(d => d.Id)
            .OrderByDescending(g => g.Count())
            .ToList();

        var html = new StringBuilder();
        html.AppendLine(GetHtmlHeader("Summary - Code Metrics Analysis"));
        html.AppendLine("<body>");
        html.AppendLine(GetNavigation("summary"));
        html.AppendLine("<div class=\"container\">");
        html.AppendLine("<h1>Issue Summary</h1>");
        
        // Add sunburst diagram
        html.AppendLine("<div class=\"chart-container\">");
        html.AppendLine("<h2>Issue Distribution (Sunburst)</h2>");
        html.AppendLine("<p>Hierarchical view: Projects &rarr; Issue Types &rarr; Severity</p>");
        html.AppendLine("<div id=\"sunburst\" style=\"display: flex; justify-content: center;\"></div>");
        html.AppendLine("</div>");
        
        html.AppendLine("<table>");
        html.AppendLine("<thead><tr><th>Issue ID</th><th>Title</th><th>Count</th><th>Severity</th></tr></thead>");
        html.AppendLine("<tbody>");
        
        foreach (var group in diagnosticGroups)
        {
            var firstDiagnostic = group.First();
            html.AppendLine("<tr>");
            html.AppendLine($"<td><code>{EscapeHtml(group.Key)}</code></td>");
            html.AppendLine($"<td>{EscapeHtml(firstDiagnostic.Title)}</td>");
            html.AppendLine($"<td><span class=\"badge badge-{GetSeverityClass(group.Count())}\">{group.Count()}</span></td>");
            html.AppendLine($"<td><span class=\"severity-{firstDiagnostic.Severity.ToLower()}\">{EscapeHtml(firstDiagnostic.Severity)}</span></td>");
            html.AppendLine("</tr>");
        }
        
        html.AppendLine("</tbody>");
        html.AppendLine("</table>");
        html.AppendLine("</div>");
        html.AppendLine(GetSunburstJavaScript(arguments));
        html.AppendLine("</body>");
        html.AppendLine("</html>");

        await File.WriteAllTextAsync(Path.Combine(outputPath, "summary.html"), html.ToString(), cancellationToken);
    }

    private async Task GenerateHistoryPageAsync(string outputPath, HistoricalDataCollection historicalData, CancellationToken cancellationToken)
    {
        var html = new StringBuilder();
        html.AppendLine(GetHtmlHeader("History - Code Metrics Analysis"));
        html.AppendLine("<body>");
        html.AppendLine(GetNavigation("history"));
        html.AppendLine("<div class=\"container\">");
        html.AppendLine("<h1>Historical Metrics</h1>");
        
        if (historicalData.Metrics.Count == 0)
        {
            html.AppendLine("<p class=\"no-issues\">No historical data available yet. Run analysis on multiple commits to see trends.</p>");
        }
        else
        {
            html.AppendLine("<div class=\"chart-container\">");
            html.AppendLine("<h2>Total Issues Over Time</h2>");
            html.AppendLine("<canvas id=\"issuesChart\"></canvas>");
            html.AppendLine("</div>");
            
            html.AppendLine("<div class=\"chart-container\">");
            html.AppendLine("<h2>Issues by Severity</h2>");
            html.AppendLine("<canvas id=\"severityChart\"></canvas>");
            html.AppendLine("</div>");
            
            // Add metric type selection section
            html.AppendLine("<div class=\"chart-container\">");
            html.AppendLine("<h2>Issue Type Trends</h2>");
            html.AppendLine("<p>Click on an issue type below to view its historical trend:</p>");
            html.AppendLine("<div id=\"metricSelector\" class=\"metric-selector\">");
            
            // Get all unique issue types across all metrics with their titles
            var allIssueTypesWithTitles = historicalData.Metrics
                .Where(m => m.IssueTypeTitles != null)
                .SelectMany(m => m.IssueTypeTitles!)
                .GroupBy(kvp => kvp.Key)
                .Select(g => new { Id = g.Key, Title = g.First().Value })
                .OrderBy(x => x.Id)
                .ToList();
            
            // Fallback to just IDs if no titles available
            if (!allIssueTypesWithTitles.Any())
            {
                var allIssueTypes = historicalData.Metrics
                    .SelectMany(m => m.IssuesByType.Keys)
                    .Distinct()
                    .OrderBy(k => k)
                    .ToList();
                    
                foreach (var issueType in allIssueTypes)
                {
                    html.AppendLine($"<button class=\"metric-button\" onclick=\"showMetricChart('{EscapeHtml(issueType)}')\" title=\"{EscapeHtml(issueType)}\">{EscapeHtml(issueType)}</button>");
                }
            }
            else
            {
                foreach (var issueType in allIssueTypesWithTitles)
                {
                    html.AppendLine($"<button class=\"metric-button\" onclick=\"showMetricChart('{EscapeHtml(issueType.Id)}')\" title=\"{EscapeHtml(issueType.Title)}\">");
                    html.AppendLine($"{EscapeHtml(issueType.Id)}<br/><small style=\"font-size: 0.85em; opacity: 0.9;\">{EscapeHtml(issueType.Title)}</small>");
                    html.AppendLine("</button>");
                }
            }
            
            html.AppendLine("</div>");
            html.AppendLine("<div id=\"metricChartContainer\" style=\"display: none; margin-top: 20px;\">");
            html.AppendLine("<h3 id=\"metricChartTitle\"></h3>");
            html.AppendLine("<canvas id=\"metricChart\"></canvas>");
            html.AppendLine("</div>");
            html.AppendLine("</div>");
            
            html.AppendLine("<h2>Commit History</h2>");
            html.AppendLine("<table>");
            html.AppendLine("<thead><tr><th>Date</th><th>Commit</th><th>Author</th><th>Total Issues</th><th>Change</th></tr></thead>");
            html.AppendLine("<tbody>");
            
            var orderedMetrics = historicalData.Metrics.OrderByDescending(m => m.CommitDate).ToList();
            for (int i = 0; i < orderedMetrics.Count; i++)
            {
                var metric = orderedMetrics[i];
                var shortHash = metric.CommitHash.Length > 8 ? metric.CommitHash.Substring(0, 8) : metric.CommitHash;
                
                html.AppendLine("<tr>");
                html.AppendLine($"<td>{metric.CommitDate:yyyy-MM-dd HH:mm}</td>");
                html.AppendLine($"<td><code>{EscapeHtml(shortHash)}</code><br/><small>{EscapeHtml(metric.CommitMessage)}</small></td>");
                html.AppendLine($"<td>{EscapeHtml(metric.CommitAuthor)}</td>");
                html.AppendLine($"<td><span class=\"badge badge-{GetSeverityClass(metric.TotalIssues)}\">{metric.TotalIssues}</span></td>");
                
                if (i < orderedMetrics.Count - 1)
                {
                    var previous = orderedMetrics[i + 1];
                    var change = metric.TotalIssues - previous.TotalIssues;
                    var changeClass = change > 0 ? "trend-negative" : change < 0 ? "trend-positive" : "trend-neutral";
                    var changeIcon = change > 0 ? "?" : change < 0 ? "?" : "?";
                    
                    html.AppendLine($"<td><span class=\"{changeClass}\">{changeIcon} {change:+#;-#;0}</span></td>");
                }
                else
                {
                    html.AppendLine("<td>-</td>");
                }
                
                html.AppendLine("</tr>");
            }
            
            html.AppendLine("</tbody>");
            html.AppendLine("</table>");
        }
        
        html.AppendLine("</div>");
        html.AppendLine(GetChartJavaScript(historicalData));
        html.AppendLine("</body>");
        html.AppendLine("</html>");

        await File.WriteAllTextAsync(Path.Combine(outputPath, "history.html"), html.ToString(), cancellationToken);
    }

    private async Task GenerateProjectPageAsync(string outputPath, ProjectDiagnosticsDto project, ResultExporterArguments arguments, CancellationToken cancellationToken)
    {
        var projectFileName = GetSafeFileName(project.Name);
        
        var html = new StringBuilder();
        html.AppendLine(GetHtmlHeader($"{project.Name} - Code Metrics Analysis"));
        html.AppendLine("<body>");
        html.AppendLine(GetNavigation(""));
        html.AppendLine("<div class=\"container\">");
        html.AppendLine($"<h1>{EscapeHtml(project.Name)}</h1>");
        html.AppendLine($"<p class=\"project-path\">{EscapeHtml(project.FilePath)}</p>");
        html.AppendLine($"<p class=\"summary\">Total Issues: <strong>{project.Diagnostics.Count}</strong></p>");

        if (project.Diagnostics.Any())
        {
            var groupedByFile = project.Diagnostics
                .GroupBy(d => d.FilePath)
                .OrderBy(g => g.Key);

            foreach (var fileGroup in groupedByFile)
            {
                html.AppendLine($"<h2>File: {EscapeHtml(Path.GetFileName(fileGroup.Key))}</h2>");
                html.AppendLine($"<p class=\"file-path\">{EscapeHtml(fileGroup.Key)}</p>");
                
                html.AppendLine("<table class=\"diagnostics-table\">");
                html.AppendLine("<thead><tr><th>Line</th><th>ID</th><th>Severity</th><th>Message</th><th>Action</th></tr></thead>");
                html.AppendLine("<tbody>");
                
                var diagnosticId = 0;
                foreach (var diagnostic in fileGroup.OrderBy(d => d.Location.Line))
                {
                    var snippetId = $"snippet_{diagnosticId}";
                    html.AppendLine("<tr>");
                    html.AppendLine($"<td><code>{diagnostic.Location.Line}:{diagnostic.Location.Character}</code></td>");
                    html.AppendLine($"<td><code>{EscapeHtml(diagnostic.Id)}</code></td>");
                    html.AppendLine($"<td><span class=\"severity-{diagnostic.Severity.ToLower()}\">{EscapeHtml(diagnostic.Severity)}</span></td>");
                    html.AppendLine($"<td>{EscapeHtml(diagnostic.Message)}</td>");
                    html.AppendLine($"<td><button class=\"toggle-snippet\" onclick=\"toggleSnippet('{snippetId}')\">Show Code</button></td>");
                    html.AppendLine("</tr>");
                    
                    html.AppendLine($"<tr id=\"{snippetId}\" class=\"code-snippet-row\" style=\"display: none;\">");
                    html.AppendLine("<td colspan=\"5\">");
                    html.AppendLine("<div class=\"code-snippet\">");
                    
                    var snippet = await GetCodeSnippetAsync(fileGroup.Key, diagnostic.Location.Line, cancellationToken);
                    if (!string.IsNullOrEmpty(snippet))
                    {
                        html.AppendLine("<pre><code>");
                        html.Append(snippet); // Don't use AppendLine since snippet already has newlines
                        html.AppendLine("</code></pre>");
                    }
                    else
                    {
                        html.AppendLine("<p class=\"snippet-error\">Unable to load code snippet</p>");
                    }
                    
                    html.AppendLine("</div>");
                    html.AppendLine("</td>");
                    html.AppendLine("</tr>");
                    
                    diagnosticId++;
                }
                
                html.AppendLine("</tbody>");
                html.AppendLine("</table>");
            }
        }
        else
        {
            html.AppendLine("<p class=\"no-issues\">No issues found in this project.</p>");
        }
        
        html.AppendLine("</div>");
        html.AppendLine(GetJavaScript());
        html.AppendLine("</body>");
        html.AppendLine("</html>");

        await File.WriteAllTextAsync(Path.Combine(outputPath, $"project_{projectFileName}.html"), html.ToString(), cancellationToken);
    }

    private async Task GenerateStylesAsync(string outputPath, CancellationToken cancellationToken)
    {
        var css = @"
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f5f5f5;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
    background-color: #fff;
    min-height: calc(100vh - 60px);
}

nav {
    background-color: #2c3e50;
    padding: 15px 20px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
}

nav ul {
    list-style: none;
    display: flex;
    gap: 20px;
    max-width: 1400px;
    margin: 0 auto;
}

nav a {
    color: #ecf0f1;
    text-decoration: none;
    padding: 5px 10px;
    border-radius: 4px;
    transition: background-color 0.3s;
}

nav a:hover, nav a.active {
    background-color: #34495e;
}

h1 {
    color: #2c3e50;
    margin-bottom: 10px;
    font-size: 2em;
}

h2 {
    color: #34495e;
    margin-top: 30px;
    margin-bottom: 15px;
    font-size: 1.5em;
    border-bottom: 2px solid #3498db;
    padding-bottom: 5px;
}

.timestamp {
    color: #7f8c8d;
    margin-bottom: 30px;
}

.trend-indicator {
    padding: 15px 20px;
    border-radius: 8px;
    margin: 20px 0;
    font-size: 1.1em;
    font-weight: bold;
}

.trend-positive {
    background-color: #d4edda;
    color: #155724;
    border-left: 4px solid #28a745;
}

.trend-negative {
    background-color: #f8d7da;
    color: #721c24;
    border-left: 4px solid #dc3545;
}

.trend-neutral {
    background-color: #d1ecf1;
    color: #0c5460;
    border-left: 4px solid #17a2b8;
}

.trend-icon {
    font-size: 1.3em;
    margin-right: 5px;
}

.summary-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 20px;
    margin: 30px 0;
}

.card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 30px;
    border-radius: 8px;
    text-align: center;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.card h3 {
    font-size: 3em;
    margin-bottom: 10px;
}

.card p {
    font-size: 1.1em;
    opacity: 0.9;
}

.chart-container {
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    margin: 30px 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.chart-container canvas {
    max-height: 400px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    background-color: white;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

thead {
    background-color: #3498db;
    color: white;
}

th, td {
    padding: 12px 15px;
    text-align: left;
    border-bottom: 1px solid #ddd;
}

tbody tr:hover {
    background-color: #f8f9fa;
}

td small {
    color: #7f8c8d;
    display: block;
    margin-top: 5px;
}

.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-weight: bold;
    font-size: 0.9em;
}

.badge-low {
    background-color: #d4edda;
    color: #155724;
}

.badge-medium {
    background-color: #fff3cd;
    color: #856404;
}

.badge-high {
    background-color: #f8d7da;
    color: #721c24;
}

.severity-error {
    color: #e74c3c;
    font-weight: bold;
}

.severity-warning {
    color: #f39c12;
    font-weight: bold;
}

.severity-info {
    color: #3498db;
    font-weight: bold;
}

.severity-hidden {
    color: #95a5a6;
}

.project-path, .file-path {
    color: #7f8c8d;
    font-size: 0.9em;
    margin-bottom: 20px;
    word-break: break-all;
}

.summary {
    font-size: 1.1em;
    margin: 20px 0;
}

.no-issues {
    padding: 40px;
    text-align: center;
    color: #27ae60;
    font-size: 1.2em;
}

code {
    background-color: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
}

a {
    color: #3498db;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

.diagnostics-table td:first-child {
    white-space: nowrap;
}

.toggle-snippet {
    background-color: #3498db;
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85em;
    transition: background-color 0.3s;
}

.toggle-snippet:hover {
    background-color: #2980b9;
}

.toggle-snippet.active {
    background-color: #e74c3c;
}

.code-snippet-row {
    background-color: #f8f9fa;
}

.code-snippet {
    padding: 15px;
    background-color: #282c34;
    border-radius: 4px;
    overflow-x: auto;
}

.code-snippet pre {
    margin: 0;
    color: #abb2bf;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 0.9em;
    line-height: 1.5;
}

.code-snippet code {
    background-color: transparent;
    color: inherit;
    padding: 0;
}

.code-snippet .highlight-line {
    background-color: rgba(231, 76, 60, 0.2);
    display: block;
    margin: 0 -15px;
    padding: 0 15px;
}

.snippet-error {
    color: #e74c3c;
    font-style: italic;
    padding: 10px;
}

.metric-selector {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 20px 0;
}

.metric-button {
    background-color: #3498db;
    color: white;
    border: none;
    padding: 10px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9em;
    font-weight: 500;
    transition: all 0.3s;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    text-align: center;
    min-width: 120px;
    line-height: 1.4;
}

.metric-button small {
    display: block;
    margin-top: 4px;
    font-weight: normal;
}

.metric-button:hover {
    background-color: #2980b9;
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.metric-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

#metricChartContainer {
    padding-top: 20px;
    border-top: 2px solid #ecf0f1;
}

#metricChartTitle {
    color: #2c3e50;
    margin-bottom: 15px;
    font-size: 1.3em;
}
";

        await File.WriteAllTextAsync(Path.Combine(outputPath, "styles.css"), css, cancellationToken);
    }

    private string GetHtmlHeader(string title)
    {
        return $@"<!DOCTYPE html>
<html lang=""en"">
<head>
    <meta charset=""UTF-8"">
    <meta name=""viewport"" content=""width=device-width, initial-scale=1.0"">
    <title>{EscapeHtml(title)}</title>
    <link rel=""stylesheet"" href=""styles.css"">
    <script src=""https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js""></script>
    <script src=""https://d3js.org/d3.v7.min.js""></script>
</head>";
    }

    private string GetNavigation(string activePage)
    {
        return $@"<nav>
    <ul>
        <li><a href=""index.html"" class=""{(activePage == "index" ? "active" : "")}"">Home</a></li>
        <li><a href=""summary.html"" class=""{(activePage == "summary" ? "active" : "")}"">Summary</a></li>
        <li><a href=""history.html"" class=""{(activePage == "history" ? "active" : "")}"">History</a></li>
    </ul>
</nav>";
    }

    private string GetChartJavaScript(HistoricalDataCollection historicalData)
    {
        var orderedMetrics = historicalData.Metrics.OrderBy(m => m.CommitDate).ToList();
        
        var labels = string.Join(",", orderedMetrics.Select(m => 
            $"'{m.CommitDate:MM/dd HH:mm}'"));
        var issuesData = string.Join(",", orderedMetrics.Select(m => m.TotalIssues));
        
        var errorData = string.Join(",", orderedMetrics.Select(m => 
            m.IssuesBySeverity.TryGetValue("Error", out var count) ? count : 0));
        var warningData = string.Join(",", orderedMetrics.Select(m => 
            m.IssuesBySeverity.TryGetValue("Warning", out var count) ? count : 0));
        var infoData = string.Join(",", orderedMetrics.Select(m => 
            m.IssuesBySeverity.TryGetValue("Info", out var count) ? count : 0));
        
        // Build historical data for all issue types as JSON
        var metricsDataJson = MetricChartHelper.BuildMetricsDataJson(orderedMetrics);
        
        return $@"<script>
const historicalMetricsData = {metricsDataJson};
let metricChartInstance = null;

// Total Issues Chart
const issuesCtx = document.getElementById('issuesChart');
if (issuesCtx) {{
    new Chart(issuesCtx, {{
        type: 'line',
        data: {{
            labels: [{labels}],
            datasets: [{{
                label: 'Total Issues',
                data: [{issuesData}],
                borderColor: '#3498db',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                tension: 0.4,
                fill: true
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: true,
            plugins: {{
                legend: {{
                    display: true,
                    position: 'top'
                }},
                tooltip: {{
                    mode: 'index',
                    intersect: false
                }}
            }},
            scales: {{
                y: {{
                    beginAtZero: true,
                    ticks: {{
                        stepSize: 1
                    }}
                }}
            }}
        }}
    }});
}}

// Severity Chart
const severityCtx = document.getElementById('severityChart');
if (severityCtx) {{
    new Chart(severityCtx, {{
        type: 'line',
        data: {{
            labels: [{labels}],
            datasets: [
                {{
                    label: 'Errors',
                    data: [{errorData}],
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    tension: 0.4
                }},
                {{
                    label: 'Warnings',
                    data: [{warningData}],
                    borderColor: '#f39c12',
                    backgroundColor: 'rgba(243, 156, 18, 0.1)',
                    tension: 0.4
                }},
                {{
                    label: 'Info',
                    data: [{infoData}],
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    tension: 0.4
                }}
            ]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: true,
            plugins: {{
                legend: {{
                    display: true,
                    position: 'top'
                }},
                tooltip: {{
                    mode: 'index',
                    intersect: false
                }}
            }},
            scales: {{
                y: {{
                    beginAtZero: true,
                    stacked: false,
                    ticks: {{
                        stepSize: 1
                    }}
                }}
            }}
        }}
    }});
}}

{MetricChartHelper.GetMetricChartScript()}
</script>";
    }

    private string GetSafeFileName(string name)
    {
        var invalid = Path.GetInvalidFileNameChars();
        return string.Join("_", name.Split(invalid, StringSplitOptions.RemoveEmptyEntries));
    }

    private string GetSeverityClass(int count)
    {
        if (count == 0) return "low";
        if (count < 10) return "low";
        if (count < 50) return "medium";
        return "high";
    }

    private string EscapeHtml(string text)
    {
        if (string.IsNullOrEmpty(text)) return string.Empty;
        
        return text
            .Replace("&", "&amp;")
            .Replace("<", "&lt;")
            .Replace(">", "&gt;")
            .Replace("\"", "&quot;")
            .Replace("'", "&#39;");
    }

    private async Task<string> GetCodeSnippetAsync(string filePath, int lineNumber, CancellationToken cancellationToken)
    {
        try
        {
            if (!File.Exists(filePath))
                return string.Empty;

            var lines = await File.ReadAllLinesAsync(filePath, cancellationToken);
            
            // Try to detect if we're looking at a method
            var methodBounds = TryFindMethodBounds(lines, lineNumber - 1);
            
            if (methodBounds.HasValue)
            {
                // Show the entire method
                var (methodStart, methodEnd) = methodBounds.Value;
                var snippet = new StringBuilder();
                
                for (int i = methodStart; i <= methodEnd && i < lines.Length; i++)
                {
                    var lineNum = i + 1;
                    var isTargetLine = lineNum == lineNumber;
                    var lineClass = isTargetLine ? " class=\"highlight-line\"" : "";
                    var prefix = isTargetLine ? "? " : "  ";
                    
                    snippet.Append($"<span{lineClass}>{EscapeHtml(prefix + $"{lineNum,4} | " + lines[i])}</span>\n");
                }
                
                return snippet.ToString();
            }
            else
            {
                // Show context lines (original behavior)
                const int contextLines = 3;
                var startLine = Math.Max(0, lineNumber - contextLines - 1);
                var endLine = Math.Min(lines.Length, lineNumber + contextLines);
                
                var snippet = new StringBuilder();
                for (int i = startLine; i < endLine; i++)
                {
                    var lineNum = i + 1;
                    var isTargetLine = lineNum == lineNumber;
                    var lineClass = isTargetLine ? " class=\"highlight-line\"" : "";
                    var prefix = isTargetLine ? "? " : "  ";
                    
                    snippet.Append($"<span{lineClass}>{EscapeHtml(prefix + $"{lineNum,4} | " + lines[i])}</span>\n");
                }
                
                return snippet.ToString();
            }
        }
        catch
        {
            return string.Empty;
        }
    }

    private (int start, int end)? TryFindMethodBounds(string[] lines, int targetLine)
    {
        if (targetLine < 0 || targetLine >= lines.Length)
            return null;

        var targetLineText = lines[targetLine].Trim();
        
        // Check if the target line looks like a method declaration
        // Look for common method patterns: access modifier + return type + method name + (
        var methodPatterns = new[]
        {
            "public ", "private ", "protected ", "internal ",
            "static ", "async ", "virtual ", "override ",
            "abstract ", "sealed "
        };
        
        var looksLikeMethod = methodPatterns.Any(p => targetLineText.Contains(p)) 
            && targetLineText.Contains("(");
        
        if (!looksLikeMethod)
        {
            // Try to find method declaration above current line
            for (int i = targetLine; i >= Math.Max(0, targetLine - 10); i--)
            {
                var line = lines[i].Trim();
                if (methodPatterns.Any(p => line.Contains(p)) && line.Contains("("))
                {
                    targetLine = i;
                    looksLikeMethod = true;
                    break;
                }
            }
        }
        
        if (!looksLikeMethod)
            return null;

        // Find the start of the method (including attributes and comments)
        int methodStart = targetLine;
        
        // Go up to find attributes ([...]) and XML comments (///)
        for (int i = targetLine - 1; i >= 0; i--)
        {
            var line = lines[i].Trim();
            
            if (string.IsNullOrWhiteSpace(line))
                continue;
                
            if (line.StartsWith("[") || line.StartsWith("///") || line.StartsWith("//"))
            {
                methodStart = i;
            }
            else
            {
                break;
            }
        }
        
        // Find the end of the method by counting braces
        int braceCount = 0;
        int methodEnd = targetLine;
        bool foundOpenBrace = false;
        
        for (int i = targetLine; i < lines.Length; i++)
        {
            var line = lines[i];
            
            // Count braces (simple approach - doesn't handle strings/comments perfectly)
            foreach (char c in line)
            {
                if (c == '{')
                {
                    braceCount++;
                    foundOpenBrace = true;
                }
                else if (c == '}')
                {
                    braceCount--;
                }
            }
            
            methodEnd = i;
            
            // If we found the opening brace and braces are balanced, we found the end
            if (foundOpenBrace && braceCount == 0)
            {
                break;
            }
            
            // Safety limit: don't go more than 200 lines
            if (i - targetLine > 200)
            {
                break;
            }
        }
        
        // Add a few lines after the closing brace if available
        methodEnd = Math.Min(methodEnd + 1, lines.Length - 1);
        
        return (methodStart, methodEnd);
    }
    
    private string GetJavaScript()
    {
        return @"<script>
function toggleSnippet(snippetId) {
    const snippetRow = document.getElementById(snippetId);
    const button = event.target;
    
    if (snippetRow.style.display === 'none') {
        snippetRow.style.display = 'table-row';
        button.textContent = 'Hide Code';
        button.classList.add('active');
    } else {
        snippetRow.style.display = 'none';
        button.textContent = 'Show Code';
        button.classList.remove('active');
    }
}
</script>";
    }
    
    private string GetSunburstJavaScript(ResultExporterArguments arguments)
    {
        // Build hierarchical data structure for sunburst
        var sunburstData = BuildSunburstData(arguments);
        
        var sb = new StringBuilder();
        sb.AppendLine("<script>");
        sb.AppendLine("console.log('Sunburst script starting...');");
        sb.AppendLine($"const sunburstData = {sunburstData};");
        sb.AppendLine("console.log('Sunburst data:', sunburstData);");
        sb.AppendLine();
        sb.AppendLine("if (typeof d3 === 'undefined') {");
        sb.AppendLine("    console.error('D3.js is not loaded!');");
        sb.AppendLine("    document.getElementById('sunburst').innerHTML = '<p style=\"text-align: center; padding: 40px; color: #e74c3c;\">D3.js library failed to load. Please check your internet connection.</p>';" );
        sb.AppendLine("} else {");
        sb.AppendLine("    console.log('D3.js version:', d3.version);");
        sb.AppendLine("    if (!sunburstData || !sunburstData.children || sunburstData.children.length === 0) {");
        sb.AppendLine("        console.warn('No data available for sunburst');");
        sb.AppendLine("        document.getElementById('sunburst').innerHTML = '<p style=\"text-align: center; padding: 40px; color: #7f8c8d;\">No data available for sunburst visualization</p>';" );
        sb.AppendLine("    } else {");
        sb.AppendLine("        console.log('Data validation passed, creating sunburst...');");
        sb.AppendLine("        try {");
        sb.AppendLine("            const width = 800;");
        sb.AppendLine("            const height = 800;");
        sb.AppendLine("            const radius = Math.min(width, height) / 2;");
        sb.AppendLine("            console.log('Creating SVG with dimensions:', width, 'x', height);");
        sb.AppendLine("            const colorScales = {");
        sb.AppendLine("                project: d3.scaleOrdinal(d3.schemeSet3),");
        sb.AppendLine("                issueType: d3.scaleOrdinal(d3.schemePastel1),");
        sb.AppendLine("                severity: d3.scaleOrdinal().domain(['Error', 'Warning', 'Info', 'Hidden']).range(['#e74c3c', '#f39c12', '#3498db', '#95a5a6'])");
        sb.AppendLine("            };");
        sb.AppendLine("            const svg = d3.select('#sunburst').append('svg').attr('width', width).attr('height', height).append('g').attr('transform', `translate(${width / 2},${height / 2})`);");
        sb.AppendLine("            console.log('SVG created');");
        sb.AppendLine("            const partition = d3.partition().size([2 * Math.PI, radius]);");
        sb.AppendLine("            const root = d3.hierarchy(sunburstData).sum(d => d.value || 0).sort((a, b) => b.value - a.value);");
        sb.AppendLine("            partition(root);");
        sb.AppendLine("            console.log('Hierarchy created, root value:', root.value);");
        sb.AppendLine("            const arc = d3.arc().startAngle(d => d.x0).endAngle(d => d.x1).innerRadius(d => d.y0).outerRadius(d => d.y1);");
        sb.AppendLine("            const arcs = root.descendants().filter(d => d.depth > 0);");
        sb.AppendLine("            console.log('Arcs to draw:', arcs.length);");
        sb.AppendLine("            svg.selectAll('path').data(arcs).enter().append('path').attr('d', arc)");
        sb.AppendLine("                .style('fill', d => { if (d.depth === 1) return colorScales.project(d.data.name); if (d.depth === 2) return colorScales.issueType(d.data.name); if (d.depth === 3) return colorScales.severity(d.data.name); return '#ccc'; })");
        sb.AppendLine("                .style('stroke', '#fff').style('stroke-width', 2).style('opacity', 0.8)");
        sb.AppendLine("                .on('mouseover', function(event, d) { d3.select(this).style('opacity', 1).style('stroke-width', 3); })");
        sb.AppendLine("                .on('mouseout', function() { d3.select(this).style('opacity', 0.8).style('stroke-width', 2); });");
        sb.AppendLine("            console.log('Arcs drawn');");
        sb.AppendLine("            svg.selectAll('text.arc-label').data(arcs).enter().append('text').attr('class', 'arc-label')");
        sb.AppendLine("                .attr('transform', d => {");
        sb.AppendLine("                    const angle = (d.x0 + d.x1) / 2 * 180 / Math.PI - 90;");
        sb.AppendLine("                    const radius = (d.y0 + d.y1) / 2;");
        sb.AppendLine("                    const rotation = angle > 90 && angle < 270 ? angle + 180 : angle;");
        sb.AppendLine("                    return `rotate(${angle}) translate(${radius},0) rotate(${rotation - angle})`;");
        sb.AppendLine("                })");
        sb.AppendLine("                .attr('text-anchor', 'middle').attr('dy', '0.35em')");
        sb.AppendLine("                .style('font-size', d => {");
        sb.AppendLine("                    const arcAngle = (d.x1 - d.x0) * 180 / Math.PI;");
        sb.AppendLine("                    const arcWidth = d.y1 - d.y0;");
        sb.AppendLine("                    if (arcAngle < 5 || arcWidth < 30) return '0px';");
        sb.AppendLine("                    if (arcAngle < 10) return '8px';");
        sb.AppendLine("                    if (arcAngle < 20) return '10px';");
        sb.AppendLine("                    return '12px';");
        sb.AppendLine("                })");
        sb.AppendLine("                .style('fill', 'white').style('font-weight', 'bold').style('text-shadow', '1px 1px 2px rgba(0,0,0,0.8)')");
        sb.AppendLine("                .style('pointer-events', 'all').style('cursor', 'help')");
        sb.AppendLine("                .text(d => {");
        sb.AppendLine("                    const arcAngle = (d.x1 - d.x0) * 180 / Math.PI;");
        sb.AppendLine("                    const arcWidth = d.y1 - d.y0;");
        sb.AppendLine("                    if (arcAngle < 5 || arcWidth < 30) return '';" );
        sb.AppendLine("                    const maxLength = Math.floor(arcAngle / 2);");
        sb.AppendLine("                    const name = d.data.name;");
        sb.AppendLine("                    if (name.length > maxLength) return name.substring(0, maxLength - 1) + '…';");
        sb.AppendLine("                    return name;");
        sb.AppendLine("                })");
        sb.AppendLine("                .append('title').text(d => {");
        sb.AppendLine("                    let path = [];");
        sb.AppendLine("                    let node = d;");
        sb.AppendLine("                    while (node.parent) {");
        sb.AppendLine("                        path.unshift(node.data.name);");
        sb.AppendLine("                        node = node.parent;");
        sb.AppendLine("                    }");
        sb.AppendLine("                    return path.join(' ? ') + '\\nCount: ' + d.value;");
        sb.AppendLine("                });");
        sb.AppendLine("            console.log('Labels added');");
        sb.AppendLine("            svg.append('text').attr('text-anchor', 'middle').attr('dy', '-0.5em').style('font-size', '24px').style('font-weight', 'bold').style('fill', '#2c3e50').text('Total Issues');");
        sb.AppendLine("            svg.append('text').attr('text-anchor', 'middle').attr('dy', '1.5em').style('font-size', '36px').style('font-weight', 'bold').style('fill', '#3498db').text(root.value);");
        sb.AppendLine("            console.log('Sunburst diagram created successfully!');");
        sb.AppendLine("        } catch (error) {");
        sb.AppendLine("            console.error('Error creating sunburst diagram:', error);");
        sb.AppendLine("            document.getElementById('sunburst').innerHTML = '<p style=\"text-align: center; padding: 40px; color: #e74c3c;\">Error creating visualization. Check console for details.</p>';" );
        sb.AppendLine("        }");
        sb.AppendLine("    }");
        sb.AppendLine("}");
        sb.AppendLine("</script>");
        
        return sb.ToString();
    }
    
    private string BuildSunburstData(ResultExporterArguments arguments)
    {
        var sb = new StringBuilder();
        sb.Append("{");
        sb.Append("\"name\":\"Root\",");
        sb.Append("\"children\":[");
        
        var projects = arguments.ProjectDiagnostics
            .Where(p => p.Diagnostics.Any())
            .OrderBy(p => p.Name)
            .ToList();
        
        for (int i = 0; i < projects.Count; i++)
        {
            if (i > 0) sb.Append(",");
            
            var project = projects[i];
            sb.Append("{");
            sb.Append($"\"name\":\"{EscapeJson(project.Name)}\",");
            sb.Append("\"children\":[");
            
            var issueGroups = project.Diagnostics
                .GroupBy(d => d.Id)
                .OrderBy(g => g.Key)
                .ToList();
            
            for (int j = 0; j < issueGroups.Count; j++)
            {
                if (j > 0) sb.Append(",");
                
                var issueGroup = issueGroups[j];
                sb.Append("{");
                sb.Append($"\"name\":\"{EscapeJson(issueGroup.Key)}\",");
                sb.Append("\"children\":[");
                
                var severityGroups = issueGroup
                    .GroupBy(d => d.Severity)
                    .OrderBy(g => g.Key)
                    .ToList();
                
                for (int k = 0; k < severityGroups.Count; k++)
                {
                    if (k > 0) sb.Append(",");
                    
                    var severityGroup = severityGroups[k];
                    sb.Append("{");
                    sb.Append($"\"name\":\"{EscapeJson(severityGroup.Key)}\",");
                    sb.Append($"\"value\":{severityGroup.Count()}");
                    sb.Append("}");
                }
                
                sb.Append("]");
                sb.Append("}");
            }
            
            sb.Append("]");
            sb.Append("}");
        }
        
        sb.Append("]");
        sb.Append("}");
        
        return sb.ToString();
    }
    
    private string EscapeJson(string text)
    {
        if (string.IsNullOrEmpty(text)) return string.Empty;
        
        return text
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\n", "\\n")
            .Replace("\r", "\\r")
            .Replace("\t", "\\t");
    }
}

