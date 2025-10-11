using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.ResultExporter
{
    public interface IResultExporter
    {
        Task ExportResultsAsync(string path, ResultExporterArguments arguments, CancellationToken cancellationToken = default);
    }
}
