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

namespace CodeMetricsAnalyzer.Analyzers
{
    [DiagnosticAnalyzer(LanguageNames.CSharp)]
    public sealed class BumpyRoadAnalyzer : MethodAnalyzer
    {
        // A "bump" starts when logic is nested at least two levels deep.
        private const int MinimumBumpDepth = 2;

        public BumpyRoadAnalyzer(AnalyzerConfiguration config) : base(config)
        {
        }

        public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics
            => ImmutableArray.Create(DiagnosticDescriptors.BumpyRoadRule);

        protected override void AnalyzeMethod(SyntaxNodeAnalysisContext context)
        {
            if (!(context.Node is MethodDeclarationSyntax methodDeclaration))
                return;

            // Skip expression-bodied members for now.
            var body = methodDeclaration.Body;
            if (body == null || body.Statements.Count == 0)
                return;

            var entries = new List<StatementEntry>();
            CollectStatements(body, currentDepth: 0, entries);

            if (entries.Count == 0)
                return;

            var bumps = DetectBumps(entries);
            if (bumps.Count == 0)
                return;

            double score = CalculateBumpyRoadScore(bumps);

            if (score > _config.BumpyRoadAnalysis.BumpynessThreshold)
            {
                ReportDiagnostics(
                    context,
                    DiagnosticDescriptors.BumpyRoadRule,
                    methodDeclaration.Identifier.GetLocation(),
                    methodDeclaration.Identifier.Text,
                    Math.Round(score, 2));
            }
        }

        private static void CollectStatements(
            StatementSyntax statement,
            int currentDepth,
            List<StatementEntry> result)
        {
            switch (statement)
            {
                case BlockSyntax block:
                    foreach (var child in block.Statements)
                    {
                        CollectStatements(child, currentDepth, result);
                    }
                    break;

                case IfStatementSyntax ifStatement:
                    AddStatement(result, ifStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);

                    CollectEmbeddedStatement(ifStatement.Statement, currentDepth + 1, result);

                    if (ifStatement.Else != null)
                    {
                        // Keep else-if on the same logical nesting level.
                        if (ifStatement.Else.Statement is IfStatementSyntax elseIf)
                        {
                            CollectStatements(elseIf, currentDepth, result);
                        }
                        else
                        {
                            CollectEmbeddedStatement(ifStatement.Else.Statement, currentDepth + 1, result);
                        }
                    }
                    break;

                case ForStatementSyntax forStatement:
                    AddStatement(result, forStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectEmbeddedStatement(forStatement.Statement, currentDepth + 1, result);
                    break;

                case ForEachStatementSyntax forEachStatement:
                    AddStatement(result, forEachStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectEmbeddedStatement(forEachStatement.Statement, currentDepth + 1, result);
                    break;

                case WhileStatementSyntax whileStatement:
                    AddStatement(result, whileStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectEmbeddedStatement(whileStatement.Statement, currentDepth + 1, result);
                    break;

                case DoStatementSyntax doStatement:
                    AddStatement(result, doStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);
                    CollectEmbeddedStatement(doStatement.Statement, currentDepth + 1, result);
                    break;

                case SwitchStatementSyntax switchStatement:
                    // Switch is debatable for Bumpy Road, but keeping it as a control contributor is a fair approximation.
                    AddStatement(result, switchStatement, currentDepth + 1, isControl: true, startsBumpCandidate: true);

                    foreach (var section in switchStatement.Sections)
                    {
                        foreach (var child in section.Statements)
                        {
                            CollectStatements(child, currentDepth + 1, result);
                        }
                    }
                    break;

                case TryStatementSyntax tryStatement:
                    CollectEmbeddedStatement(tryStatement.Block, currentDepth, result);

                    foreach (var catchClause in tryStatement.Catches)
                    {
                        CollectEmbeddedStatement(catchClause.Block, currentDepth + 1, result);
                    }

                    if (tryStatement.Finally != null)
                    {
                        CollectEmbeddedStatement(tryStatement.Finally.Block, currentDepth, result);
                    }
                    break;

                default:
                    AddStatement(result, statement, currentDepth, isControl: false, startsBumpCandidate: false);
                    break;
            }
        }

        private static void CollectEmbeddedStatement(
            StatementSyntax statement,
            int currentDepth,
            List<StatementEntry> result)
        {
            CollectStatements(statement, currentDepth, result);
        }

        private static void AddStatement(
            List<StatementEntry> result,
            StatementSyntax statement,
            int depth,
            bool isControl,
            bool startsBumpCandidate)
        {
            var span = statement.SyntaxTree.GetLineSpan(statement.Span);
            int startLine = span.StartLinePosition.Line;
            int endLine = span.EndLinePosition.Line;

            result.Add(new StatementEntry(
                statement,
                depth,
                isControl,
                startsBumpCandidate,
                startLine,
                endLine));
        }

        private static List<BumpRegion> DetectBumps(List<StatementEntry> statements)
        {
            var ordered = statements
                .OrderBy(s => s.StartLine)
                .ThenBy(s => s.EndLine)
                .ToList();

            var bumps = new List<BumpRegion>();

            foreach (var anchor in ordered.Where(s => s.StartsBumpCandidate && s.Depth >= MinimumBumpDepth))
            {
                var bump = CreateBumpFromAnchor(anchor, ordered);
                if (bump == null)
                    continue;

                if (bumps.Count > 0 && bump.StartLine <= bumps[bumps.Count - 1].EndLine)
                {
                    MergeInto(bumps[bumps.Count - 1], bump);
                }
                else
                {
                    bumps.Add(bump);
                }
            }

            return bumps;
        }

        private static BumpRegion CreateBumpFromAnchor(
            StatementEntry anchor,
            List<StatementEntry> orderedStatements)
        {
            var bumpStatements = orderedStatements
                .Where(s =>
                    s.StartLine >= anchor.StartLine &&
                    s.EndLine <= anchor.EndLine &&
                    s.Depth >= MinimumBumpDepth)
                .ToList();

            if (bumpStatements.Count == 0)
                return null;

            int startLine = bumpStatements.Min(s => s.StartLine);
            int endLine = bumpStatements.Max(s => s.EndLine);

            var bump = new BumpRegion(startLine, endLine);
            bump.Statements.AddRange(bumpStatements);
            return bump;
        }

        private static void MergeInto(BumpRegion target, BumpRegion source)
        {
            target.StartLine = Math.Min(target.StartLine, source.StartLine);
            target.EndLine = Math.Max(target.EndLine, source.EndLine);

            foreach (var statement in source.Statements)
            {
                if (!target.Statements.Any(existing =>
                    existing.StartLine == statement.StartLine &&
                    existing.EndLine == statement.EndLine &&
                    existing.Depth == statement.Depth &&
                    ReferenceEquals(existing.Statement, statement.Statement)))
                {
                    target.Statements.Add(statement);
                }
            }
        }

        private static double CalculateBumpyRoadScore(List<BumpRegion> bumps)
        {
            double total = 0;

            foreach (var bump in bumps)
            {
                int maxDepth = bump.Statements.Max(s => s.Depth);
                int nestedControlCount = bump.Statements.Count(s => s.IsControl && s.Depth >= MinimumBumpDepth);
                int bumpLines = bump.EndLine - bump.StartLine + 1;

                double bumpScore =
                    (maxDepth * 3.0) +
                    (nestedControlCount * 2.0) +
                    (bumpLines * 0.5);

                total += bumpScore;
            }

            // Explicitly penalize multiple bumps in the same method.
            total += (bumps.Count - 1) * 4.0;

            return total;
        }

        private sealed class StatementEntry
        {
            public StatementEntry(
                StatementSyntax statement,
                int depth,
                bool isControl,
                bool startsBumpCandidate,
                int startLine,
                int endLine)
            {
                Statement = statement;
                Depth = depth;
                IsControl = isControl;
                StartsBumpCandidate = startsBumpCandidate;
                StartLine = startLine;
                EndLine = endLine;
            }

            public StatementSyntax Statement { get; }
            public int Depth { get; }
            public bool IsControl { get; }
            public bool StartsBumpCandidate { get; }
            public int StartLine { get; }
            public int EndLine { get; }
        }

        private sealed class BumpRegion
        {
            public BumpRegion(int startLine, int endLine)
            {
                StartLine = startLine;
                EndLine = endLine;
            }

            public int StartLine { get; set; }
            public int EndLine { get; set; }
            public List<StatementEntry> Statements { get; } = new List<StatementEntry>();
        }
    }
}