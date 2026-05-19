using System.Collections.Immutable;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class FunctionParameterCountAnalyzer : MethodAnalyzer
    {
        public FunctionParameterCountAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.FunctionParameterCountRule);

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            if (!TryGetMemberComponents(context.Node,
                    out var identifier, out _, out _, out var parameterList))
                return;

            // Accessors have no parameter list — nothing to count.
            if (parameterList == null)
                return;

            int parameterCount = parameterList.Parameters
                .Count(p => !p.Modifiers.Any(m => m.IsKind(SyntaxKind.ThisKeyword)));

            if (parameterCount > _config.FunctionParameterCountAnalysis.ParameterCountThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.FunctionParameterCountRule,
                    identifier.GetLocation(),
                    identifier.Text,
                    parameterCount,
                    _config.FunctionParameterCountAnalysis.ParameterCountThreshold);
            }
        }
    }
}
