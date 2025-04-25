using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.Analyzers.Configurations
{
    public class LCOM4AnalysisConfiguration
    {
        public double CohesionThreshold { get; init; }
        public int MinimumMethodCount { get; init; }
        public int MinimumFieldCount { get; init; }
    }
}
