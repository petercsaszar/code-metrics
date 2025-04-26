using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;
using System.Collections.Immutable;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class FunctionParameterCountAnalyzer(AnalyzerConfiguration config) : MethodAnalyzer(config)
    {
        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => [DiagnosticDescriptors.FunctionParameterCountRule];


        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;
            int parameterCount = methodDeclaration.ParameterList.Parameters.Count;

            if (parameterCount > _config.FunctionParameterCountAnalysis.ParameterCountThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.FunctionParameterCountRule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    parameterCount,
                    _config.FunctionParameterCountAnalysis.ParameterCountThreshold);
            }
        }
    }
}
