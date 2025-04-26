namespace CodeMetricsAnalyzer.Analyzers.Configurations
{
    public class AnalyzerConfiguration
    {
        public BumpyRoadAnalysisConfiguration BumpyRoadAnalysis { get; init; }
        public FunctionParameterCountAnalysisConfiguration FunctionParameterCountAnalysis { get; init; }
        public LCOM4AnalysisConfiguration LCOM4Analysis { get; init; }
        public LCOM5AnalysisConfiguration LCOM5Analysis { get; init; }
    }
}
