namespace CodeMetricsAnalyzer.ResultExporter.DTOs;

public class ProjectDiagnosticsDto
{
    public required string Name { get; set; }
    public required string FilePath { get; set; }
    public required List<DiagnosticDto> Diagnostics { get; set; }
}
