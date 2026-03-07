namespace CodeMetricsAnalyzer.Analyzers.Configurations
{
    public class AnalyzerConfiguration
    {
        public BumpyRoadAnalysisConfiguration BumpyRoadAnalysis { get; set; }
        public FunctionParameterCountAnalysisConfiguration FunctionParameterCountAnalysis { get; set; }
        public LCOM4AnalysisConfiguration LCOM4Analysis { get; set; }
        public LCOM5AnalysisConfiguration LCOM5Analysis { get; set; }
        public MaintainabilityIndexAnalysisConfiguration MaintainabilityIndexAnalysis { get; set; }
        public CyclomaticComplexityAnalysisConfiguration CyclomaticComplexityAnalysis { get; set; }
        public ClassCouplingAnalysisConfiguration ClassCouplingAnalysis { get; set; }
    }
}
