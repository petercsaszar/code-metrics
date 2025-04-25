using CodeMetricsAnalyzer.Analyzers.Configurations;
using Microsoft.CodeAnalysis.Diagnostics;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.Analyzers
{
    public static class AnalyzerFactory
    {
        public static ImmutableArray<DiagnosticAnalyzer> CreateAnalyzers(AnalyzerConfiguration config)
        {
            return
            [
                new BumpyRoadAnalyzer(config),
                new FunctionParameterCountAnalyzer(config),
                new LCOM4Analyzer(config),
                new LCOM5Analyzer(config)
            ];
        }
    }
}
