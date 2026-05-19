using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace CodeMetricsAnalyzer.Analyzers.Configurations
{
    public class LCOM4AnalysisConfiguration
    {
        public int CohesionThreshold { get; set; } = 4;
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
