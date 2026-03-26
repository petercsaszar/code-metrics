using System.Collections.Immutable;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;
using Microsoft.CodeAnalysis.Operations;

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
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;

            if (methodDeclaration.Body is null && methodDeclaration.ExpressionBody is null)
                return;

            var model = context.SemanticModel;

            var methodBodyOp = model.GetOperation(methodDeclaration, context.CancellationToken) as IMethodBodyOperation;

            // fallback
            IOperation rootOp = methodBodyOp?.BlockBody ?? methodBodyOp?.ExpressionBody;
            if (rootOp is null)
                rootOp = methodDeclaration.Body != null
                    ? model.GetOperation(methodDeclaration.Body, context.CancellationToken)
                    : model.GetOperation(methodDeclaration.ExpressionBody.Expression, context.CancellationToken);

            if (rootOp is null)
                return;

            int complexity = MetricsHelper.CalculateCyclomaticComplexity(rootOp);

            if (complexity > _config.CyclomaticComplexityAnalysis.MaximumComplexity)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.CyclomaticComplexityRule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    complexity);
            }
        }

    }
}