using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Diagnostics;

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public class BumpyRoadAnalyzer : DiagnosticAnalyzer
    {
        private static readonly DiagnosticDescriptor Rule = new DiagnosticDescriptor(
            id: "BR001",
            title: "Bumpy Road Code Smell",
            messageFormat: "Method '{0}' has a high bumpy road score ({1:F2}). Consider refactoring deeply nested structures.",
            category: "CodeSmell",
            defaultSeverity: DiagnosticSeverity.Warning,
            isEnabledByDefault: true,
            description: "This method has a high level of statement nesting, making it harder to read.");

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => ImmutableArray.Create(Rule);

        public override void Initialize(AnalysisContext context)
        {
            context.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
            context.EnableConcurrentExecution();
            context.RegisterSyntaxNodeAction(AnalyzeMethod, SyntaxKind.MethodDeclaration);
        }

        private void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            var methodDeclaration = (MethodDeclarationSyntax)context.Node;
            var body = methodDeclaration.Body;

            if (body == null || !body.Statements.Any())
            {
                // If the function is empty, the metric is defined to be 1.
                // ReportBumpyRoad(context, methodDeclaration, 1);
                return;
            }

            // Compute depth for each statement
            var statementDepths = new List<int>();
            ComputeStatementDepths(body, 0, statementDepths); // Start depth at 0 (method level)

            int statementCount = statementDepths.Count;
            if (statementCount == 0)
            {
                // ReportBumpyRoad(context, methodDeclaration, 1);
                return;
            }

            // Compute the Bumpy Road metric
            double totalBumpiness = statementDepths.Sum();
            double bumpyRoadMetric = totalBumpiness / statementCount;

            // Get max depth
            int maxDepth = statementDepths.Max();
            double normalizedScore = Math.Clamp(bumpyRoadMetric, 1, maxDepth);

            // If the metric is high, report the issue
            if (normalizedScore > 2) // threshold
            {
                ReportBumpyRoad(context, methodDeclaration, normalizedScore);
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

                // Recursively check nested statements with increased depth
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

        private void ReportBumpyRoad(SyntaxNodeAnalysisContext context, MethodDeclarationSyntax methodDeclaration, double score)
        {
            var diagnostic = Diagnostic.Create(
                Rule,
                methodDeclaration.Identifier.GetLocation(),
                methodDeclaration.Identifier.Text,
                score);

            context.ReportDiagnostic(diagnostic);
        }
    }
}