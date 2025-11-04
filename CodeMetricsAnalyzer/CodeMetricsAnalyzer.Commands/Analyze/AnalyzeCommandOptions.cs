using CodeMetricsAnalyzer.Analyzers.Configurations;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.Commands.Analyze
{
    public class AnalyzeCommandOptions
    {
        public FileInfo Source { get; set; } = null!;
        public string? Output { get; set; }
        public string? MSBuildPath { get; set; }
        public required AnalyzerConfiguration AnalyzerConfiguration { get; set; }
    }
}
