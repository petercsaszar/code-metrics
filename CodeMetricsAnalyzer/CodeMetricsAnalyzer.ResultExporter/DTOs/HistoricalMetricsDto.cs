using System.Text.Json;
using System.Xml.Linq;

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
    public Dictionary<string, string>? IssueTypeTitles { get; set; }

    public async Task SaveAsXmlAsync(string filePath, CancellationToken cancellationToken = default)
    {
        var doc = new XDocument(
            new XElement("HistoricalMetrics",
                new XElement("CommitHash", CommitHash),
                new XElement("CommitMessage", CommitMessage),
                new XElement("CommitAuthor", CommitAuthor),
                new XElement("CommitDate", CommitDate.ToString("o")),
                new XElement("TotalIssues", TotalIssues),
                new XElement("ProjectCount", ProjectCount),
                new XElement("UniqueIssueTypes", UniqueIssueTypes),
                new XElement("IssuesByType",
                    IssuesByType.Select(kvp => 
                        new XElement("Issue",
                            new XAttribute("Id", kvp.Key),
                            new XAttribute("Count", kvp.Value),
                            IssueTypeTitles != null && IssueTypeTitles.ContainsKey(kvp.Key) 
                                ? new XAttribute("Title", IssueTypeTitles[kvp.Key])
                                : null))),
                new XElement("IssuesBySeverity",
                    IssuesBySeverity.Select(kvp =>
                        new XElement("Severity",
                            new XAttribute("Level", kvp.Key),
                            new XAttribute("Count", kvp.Value)))))
        );

        await Task.Run(() => doc.Save(filePath), cancellationToken);
    }

    public static HistoricalMetricsDto? LoadFromXml(string filePath)
    {
        try
        {
            var doc = XDocument.Load(filePath);
            var root = doc.Element("HistoricalMetrics");
            if (root == null) return null;

            var issuesByType = root.Element("IssuesByType")?
                .Elements("Issue")
                .ToDictionary(
                    e => e.Attribute("Id")?.Value ?? "",
                    e => int.Parse(e.Attribute("Count")?.Value ?? "0"))
                ?? new Dictionary<string, int>();

            var issueTypeTitles = root.Element("IssuesByType")?
                .Elements("Issue")
                .Where(e => e.Attribute("Title") != null)
                .ToDictionary(
                    e => e.Attribute("Id")?.Value ?? "",
                    e => e.Attribute("Title")?.Value ?? "")
                ?? new Dictionary<string, string>();

            var issuesBySeverity = root.Element("IssuesBySeverity")?
                .Elements("Severity")
                .ToDictionary(
                    e => e.Attribute("Level")?.Value ?? "",
                    e => int.Parse(e.Attribute("Count")?.Value ?? "0"))
                ?? new Dictionary<string, int>();

            return new HistoricalMetricsDto
            {
                CommitHash = root.Element("CommitHash")?.Value ?? "",
                CommitMessage = root.Element("CommitMessage")?.Value ?? "",
                CommitAuthor = root.Element("CommitAuthor")?.Value ?? "",
                CommitDate = DateTime.Parse(root.Element("CommitDate")?.Value ?? DateTime.Now.ToString("o")),
                TotalIssues = int.Parse(root.Element("TotalIssues")?.Value ?? "0"),
                ProjectCount = int.Parse(root.Element("ProjectCount")?.Value ?? "0"),
                UniqueIssueTypes = int.Parse(root.Element("UniqueIssueTypes")?.Value ?? "0"),
                IssuesByType = issuesByType,
                IssuesBySeverity = issuesBySeverity,
                IssueTypeTitles = issueTypeTitles.Count > 0 ? issueTypeTitles : null
            };
        }
        catch
        {
            return null;
        }
    }
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

    public static HistoricalDataCollection LoadFromDirectory(string directoryPath)
    {
        var collection = new HistoricalDataCollection();
        
        if (!Directory.Exists(directoryPath))
            return collection;

        // Load all files first, then sort by commit date before taking the 100 most recent.
        // Sorting by file write time before parsing would pick the wrong 100 entries if
        // files were copied or the filesystem timestamps were modified.
        var xmlFiles = Directory.GetFiles(directoryPath, "*.xml");

        foreach (var file in xmlFiles)
        {
            var metric = HistoricalMetricsDto.LoadFromXml(file);
            if (metric != null)
                collection.Metrics.Add(metric);
        }

        collection.Metrics = collection.Metrics
            .OrderByDescending(m => m.CommitDate)
            .Take(100)
            .ToList();

        return collection;
    }
}
