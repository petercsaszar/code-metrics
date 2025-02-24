namespace CodeMetricsAnalyzer.ResultExporter.DTOs;

public class ProjectDiagnosticsDto
{
    public string Name { get; set; }
    public string FilePath { get; set; }
    public List<DiagnosticDto> Diagnostics { get; set; }
}
