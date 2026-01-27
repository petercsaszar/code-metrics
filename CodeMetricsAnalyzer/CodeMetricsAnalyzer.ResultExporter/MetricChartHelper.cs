using CodeMetricsAnalyzer.ResultExporter.DTOs;
using System.Text;

namespace CodeMetricsAnalyzer.ResultExporter;

public static class MetricChartHelper
{
    public static string BuildMetricsDataJson(List<HistoricalMetricsDto> orderedMetrics)
    {
        var labels = orderedMetrics.Select(m => m.CommitDate.ToString("MM/dd HH:mm")).ToList();
        
        var metricsJson = new StringBuilder();
        metricsJson.Append("{");
        metricsJson.Append("\"labels\":[");
        metricsJson.Append(string.Join(",", labels.Select(l => $"\"{l}\"")));
        metricsJson.Append("],");
        metricsJson.Append("\"metrics\":[");
        
        for (int i = 0; i < orderedMetrics.Count; i++)
        {
            if (i > 0) metricsJson.Append(",");
            
            var metric = orderedMetrics[i];
            metricsJson.Append("{");
            metricsJson.Append("\"issuesByType\":{");
            
            var issueTypeItems = metric.IssuesByType.Select(kvp => 
                $"\"{EscapeJson(kvp.Key)}\":{kvp.Value}");
            metricsJson.Append(string.Join(",", issueTypeItems));
            
            metricsJson.Append("}");
            metricsJson.Append("}");
        }
        
        metricsJson.Append("]");
        metricsJson.Append("}");
        
        return metricsJson.ToString();
    }
    
    private static string EscapeJson(string text)
    {
        if (string.IsNullOrEmpty(text)) return string.Empty;
        
        return text
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\n", "\\n")
            .Replace("\r", "\\r")
            .Replace("\t", "\\t");
    }
    
    public static string GetMetricChartScript()
    {
        return @"
// Function to show individual metric chart
function showMetricChart(metricId) {
    const container = document.getElementById('metricChartContainer');
    const title = document.getElementById('metricChartTitle');
    const canvas = document.getElementById('metricChart');
    
    // Show container
    container.style.display = 'block';
    title.textContent = 'Trend for ' + metricId;
    
    // Extract data for this metric
    const metricData = historicalMetricsData.metrics.map(m => m.issuesByType[metricId] || 0);
    
    // Destroy existing chart if any
    if (metricChartInstance) {
        metricChartInstance.destroy();
    }
    
    // Create new chart
    metricChartInstance = new Chart(canvas, {
        type: 'line',
        data: {
            labels: historicalMetricsData.labels,
            datasets: [{
                label: metricId,
                data: metricData,
                borderColor: '#9b59b6',
                backgroundColor: 'rgba(155, 89, 182, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
    
    // Scroll to chart
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}";
    }
}
