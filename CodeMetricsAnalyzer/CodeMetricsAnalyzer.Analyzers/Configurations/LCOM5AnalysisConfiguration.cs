using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.Analyzers.Configurations
{
    public class LCOM5AnalysisConfiguration
    {
        public double CohesionThreshold { get; set; } = 0.5;
        public int MinimumMethodCount { get; set; } = 2;
        public int MinimumMemberCount { get; set; } = 1;

        // Legacy alias kept for JSON backwards-compat; MinimumMemberCount takes precedence when non-zero.
        public int MinimumFieldCount
        {
            get => MinimumMemberCount;
            set => MinimumMemberCount = value;
        }
    }
}
