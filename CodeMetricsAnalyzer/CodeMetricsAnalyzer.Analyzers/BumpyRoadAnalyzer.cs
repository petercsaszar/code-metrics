using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using CodeMetricsAnalyzer.Analyzers.BaseAnalyzers;
using CodeMetricsAnalyzer.Analyzers.Configurations;
using CodeMetricsAnalyzer.Analyzers.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class BumpyRoadAnalyzer(AnalyzerConfiguration config) : MethodAnalyzer(config)
    {
        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => [DiagnosticDescriptors.BumpyRoadRule];

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;
            var body = methodDeclaration.Body;

            if (body == null || !body.Statements.Any())
            {
                // Empty body is not evaluated
                return;
            }

            // Compute depth for each statement
            var statementDepths = new List<int>();
            ComputeStatementDepths(body, 0, statementDepths);

            int statementCount = statementDepths.Count;
            if (statementCount == 0)
            {
                // zero statements count should not be evaluated
                return;
            }

            double totalBumpiness = statementDepths.Sum();
            double bumpyRoadMetric = totalBumpiness / statementCount;

            if (bumpyRoadMetric > _config.BumpyRoadAnalysis.BumpynessThreshold) // threshold
            {
                ReportDiagnostics(
                    context, 
                    DiagnosticDescriptors.BumpyRoadRule, 
                    methodDeclaration.Identifier.GetLocation(), 
                    methodDeclaration.Identifier.Text, 
                    bumpyRoadMetric);
            }
        }

        private void ComputeStatementDepths(SyntaxNode node, int currentDepth, List<int> depths)
        {
            foreach (var child in node.ChildNodes())
            {
                if (IsConsideredStatement(child))
                {
                    depths.Add(currentDepth + 1);
                }

                ComputeStatementDepths(child, currentDepth + 1, depths);
            }
        }

        private bool IsConsideredStatement(SyntaxNode node)
        {
            return node is StatementSyntax && node.Kind() is
                SyntaxKind.IfStatement or SyntaxKind.ForStatement or SyntaxKind.WhileStatement or
                 SyntaxKind.DoStatement or SyntaxKind.SwitchStatement or SyntaxKind.Block or
                 SyntaxKind.LocalDeclarationStatement or SyntaxKind.ExpressionStatement;
        }
    }
}