namespace CodeMetricsAnalyzer.Analyzers.Configurations
{
    public class AnalyzerConfiguration
    {
        public BumpyRoadAnalysisConfiguration BumpyRoadAnalysis { get; set; } = new BumpyRoadAnalysisConfiguration();
        public FunctionParameterCountAnalysisConfiguration FunctionParameterCountAnalysis { get; set; } = new FunctionParameterCountAnalysisConfiguration();
        public LCOM4AnalysisConfiguration LCOM4Analysis { get; set; } = new LCOM4AnalysisConfiguration();
        public LCOM5AnalysisConfiguration LCOM5Analysis { get; set; } = new LCOM5AnalysisConfiguration();
        public MaintainabilityIndexAnalysisConfiguration MaintainabilityIndexAnalysis { get; set; } = new MaintainabilityIndexAnalysisConfiguration();
        public CyclomaticComplexityAnalysisConfiguration CyclomaticComplexityAnalysis { get; set; } = new CyclomaticComplexityAnalysisConfiguration();
        public ClassCouplingAnalysisConfiguration ClassCouplingAnalysis { get; set; } = new ClassCouplingAnalysisConfiguration();
    }
}
