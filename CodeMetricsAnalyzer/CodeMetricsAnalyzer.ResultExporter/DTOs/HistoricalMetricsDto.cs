using System.Text.Json;

namespace CodeMetricsAnalyzer.ResultExporter.DTOs;

public class HistoricalMetricsDto
{
    public required string CommitHash { get; set; }
    public required string CommitMessage { get; set; }
    public required string CommitAuthor { get; set; }
    public required DateTime CommitDate { get; set; }
    public required int TotalIssues { get; set; }
    public required int ProjectCount { get; set; }
    public required int UniqueIssueTypes { get; set; }
    public required Dictionary<string, int> IssuesByType { get; set; }
    public required Dictionary<string, int> IssuesBySeverity { get; set; }
}

public class HistoricalDataCollection
{
    public List<HistoricalMetricsDto> Metrics { get; set; } = new();
    
    public async Task SaveAsync(string filePath, CancellationToken cancellationToken = default)
    {
        var json = JsonSerializer.Serialize(this, new JsonSerializerOptions 
        { 
            WriteIndented = true 
        });
        await File.WriteAllTextAsync(filePath, json, cancellationToken);
    }
    
    public static async Task<HistoricalDataCollection> LoadAsync(string filePath, CancellationToken cancellationToken = default)
    {
        if (!File.Exists(filePath))
            return new HistoricalDataCollection();
            
        var json = await File.ReadAllTextAsync(filePath, cancellationToken);
        return JsonSerializer.Deserialize<HistoricalDataCollection>(json) ?? new HistoricalDataCollection();
    }
}
