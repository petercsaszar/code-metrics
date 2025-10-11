namespace CodeMetricsAnalyzer.ResultExporter.DTOs;

public class DiagnosticDto
{
    public required string Id { get; set; }
    public required string Severity { get; set; }
    public required string Title { get; set; }
    public required string Description { get; set; }
    public required string Message { get; set; }
    public required string FilePath { get; set; }
    public required LocationDto Location { get; set; }
}
