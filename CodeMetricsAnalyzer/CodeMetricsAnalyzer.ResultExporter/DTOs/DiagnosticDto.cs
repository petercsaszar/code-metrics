namespace CodeMetricsAnalyzer.ResultExporter.DTOs;

public class DiagnosticDto
{
    public string Id { get; set; }
    public string Severity { get; set; }
    public string Title { get; set; }
    public string Description { get; set; }
    public string Message { get; set; }
    public string FilePath { get; set; }
    public LocationDto Location { get; set; }
}
