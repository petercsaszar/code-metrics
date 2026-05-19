using System;
using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class MaintainabilityIndexAnalyzer : MethodAnalyzer
    {
        // Oman & Hagemeister (1992) formula coefficients, Microsoft-normalized variant (0–100 scale).
        private const double MiMax = 171.0;
        private const double HalsteadCoefficient = 5.2;
        private const double CyclomaticCoefficient = 0.23;
        private const double LoCCoefficient = 16.2;

        public MaintainabilityIndexAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.MaintainabilityIndexRule);

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            if (!TryGetMemberComponents(context.Node,
                    out var identifier, out _, out _, out _))
                return;

            var rootOp = GetMemberOperation(context.SemanticModel, context.Node, context.CancellationToken);
            if (rootOp == null)
                return;

            double halsteadVolume = MetricsHelper.CalculateHalsteadVolume(rootOp);
            int cyclomaticComplexity = MetricsHelper.CalculateCyclomaticComplexity(rootOp);
            int linesOfCode = MetricsHelper.CalculateLinesOfCode(context.Node);

            double mi = MiMax;

            if (halsteadVolume > 0)
                mi -= HalsteadCoefficient * Math.Log(halsteadVolume);

            mi -= CyclomaticCoefficient * cyclomaticComplexity;

            if (linesOfCode > 0)
                mi -= LoCCoefficient * Math.Log(linesOfCode);

            mi = Math.Max(0, (mi / MiMax) * 100.0);

            if (mi < _config.MaintainabilityIndexAnalysis.MinimumMaintainabilityIndex)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.MaintainabilityIndexRule,
                    identifier.GetLocation(),
                    identifier.Text,
                    Math.Round(mi, 2));
            }
        }
    }
}
