using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class CyclomaticComplexityAnalyzer : MethodAnalyzer
    {
        public CyclomaticComplexityAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.CyclomaticComplexityRule);

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            if (!TryGetMemberComponents(context.Node,
                    out var identifier, out _, out _, out _))
                return;

            var rootOp = GetMemberOperation(context.SemanticModel, context.Node, context.CancellationToken);
            if (rootOp == null)
                return;

            int complexity = MetricsHelper.CalculateCyclomaticComplexity(rootOp);

            if (complexity > _config.CyclomaticComplexityAnalysis.MaximumComplexity)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.CyclomaticComplexityRule,
                    identifier.GetLocation(),
                    identifier.Text,
                    complexity);
            }
        }
    }
}
