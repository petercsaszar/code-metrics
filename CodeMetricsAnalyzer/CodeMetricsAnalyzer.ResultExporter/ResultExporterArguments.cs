using CodeMetricsAnalyzer.ResultExporter.DTOs;

namespace CodeMetricsAnalyzer.ResultExporter;

public class ResultExporterArguments
{
    // public string CodeMetrics { get; set; }
    public List<ProjectDiagnosticsDto> ProjectDiagnostics { get; set; }
}
