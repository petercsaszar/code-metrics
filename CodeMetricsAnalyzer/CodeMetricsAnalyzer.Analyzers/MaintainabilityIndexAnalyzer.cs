using System;
using System.Collections.Generic;
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
    public class MaintainabilityIndexAnalyzer : MethodAnalyzer
    {
        public MaintainabilityIndexAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.MaintainabilityIndexRule);

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;

            if (methodDeclaration.Body is null && methodDeclaration.ExpressionBody is null)
                return;

            var semanticModel = context.SemanticModel;

            var methodBodyOperation =
                semanticModel.GetOperation(methodDeclaration, context.CancellationToken) as IMethodBodyOperation;

            IOperation rootOperation =
                methodBodyOperation?.BlockBody ??
                methodBodyOperation?.ExpressionBody ??
                (methodDeclaration.Body != null
                    ? semanticModel.GetOperation(methodDeclaration.Body, context.CancellationToken)
                    : null);

            if (rootOperation is null)
                return;

            double halsteadVolume = MetricsHelper.CalculateHalsteadVolume(rootOperation);
            int cyclomaticComplexity = MetricsHelper.CalculateCyclomaticComplexity(rootOperation);
            int linesOfCode = MetricsHelper.CalculateLinesOfCode(methodDeclaration);

            double maintainabilityIndex = 171.0;

            if (halsteadVolume > 0)
            {
                maintainabilityIndex -= 5.2 * Math.Log(halsteadVolume);
            }

            maintainabilityIndex -= 0.23 * cyclomaticComplexity;

            if (linesOfCode > 0)
            {
                maintainabilityIndex -= 16.2 * Math.Log(linesOfCode);
            }

            maintainabilityIndex = Math.Max(0, (maintainabilityIndex / 171.0) * 100.0);

            if (maintainabilityIndex < _config.MaintainabilityIndexAnalysis.MinimumMaintainabilityIndex)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.MaintainabilityIndexRule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    Math.Round(maintainabilityIndex, 2));
            }
        }

        

        
    }
}